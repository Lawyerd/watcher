"""[v3.0] 휴대폰 푸시 알림 (Web Push — VAPID 서명 RFC 8292 + aes128gcm 암호화 RFC 8291).
pywebpush 대신 이미 쓰는 cryptography만으로 직접 구현한다 (의존성·빌드 크기 최소화).

- 휴대폰 페이지가 서비스 워커로 구독하면 원격 서버(/api/push)가 구독 정보를 push.json에 저장한다.
- 알람 발생·가공 완료 때 notifier가 send()를 부르면, 📡 원격 모니터링이 켜져 있을 때만 보낸다.
- 보내는 곳은 브라우저 회사의 푸시 서버(구글·애플·모질라·MS)뿐 — 구독 주소를 그 도메인으로만 허용해
  로그인한 사람이라도 이 PC가 임의 주소로 요청을 보내게 만들 수 없게 한다."""
import os
import ssl
import json
import time
import queue
import base64
import struct
import logging
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
try:
    import certifi
except ImportError:
    certifi = None

logger = logging.getLogger(__name__)


def _ssl_context():
    """윈도우 인증서 저장소 + certifi 인증서 묶음.
    윈도우는 루트 인증서를 필요할 때 내려받는데(CryptoAPI) 파이썬(OpenSSL)은 그걸 못 해서,
    애플 푸시 서버(web.push.apple.com) 인증서 확인이 CERTIFICATE_VERIFY_FAILED로 실패했다 (실측, 구글은 통과)."""
    ctx = ssl.create_default_context()
    if certifi:
        ctx.load_verify_locations(certifi.where())
    return ctx


SSL_CTX = _ssl_context()

PUSH_HOSTS = ("fcm.googleapis.com", ".push.apple.com", ".push.services.mozilla.com", ".notify.windows.com")
MAX_SUBS = 10          # 휴대폰 여러 대까지 (넘치면 오래된 것부터 지움)
TTL_SEC = 6 * 3600     # 휴대폰이 꺼져 있으면 푸시 서버가 이만큼 들고 있다가 전달
KINDS = ("alarm", "done")


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _point(key):
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def valid_endpoint(url):
    u = urlsplit(str(url))
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or (h.startswith(".") and host.endswith(h)) for h in PUSH_HOSTS)


def encrypt(payload, p256dh, auth):
    """RFC 8291: 휴대폰 공개키와 ECDH로 키를 만들어 AES-128-GCM 한 레코드로 암호화"""
    ua_pub, secret = _unb64(p256dh), _unb64(auth)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub)
    as_key = ec.generate_private_key(ec.SECP256R1())
    as_pub = _point(as_key.public_key())
    ikm = HKDF(hashes.SHA256(), 32, salt=secret, info=b"WebPush: info\x00" + ua_pub + as_pub).derive(
        as_key.exchange(ec.ECDH(), ua_key))
    salt = os.urandom(16)
    cek = HKDF(hashes.SHA256(), 16, salt=salt, info=b"Content-Encoding: aes128gcm\x00").derive(ikm)
    nonce = HKDF(hashes.SHA256(), 12, salt=salt, info=b"Content-Encoding: nonce\x00").derive(ikm)
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)   # \x02 = 마지막 레코드 구분자
    return salt + struct.pack("!I", 4096) + bytes([len(as_pub)]) + as_pub + body


class PushSender:
    def __init__(self, path=None, enabled=lambda: True):
        self.path = path
        self.enabled = enabled            # 📡 원격 모니터링이 켜져 있는지 (main에서 넘김)
        self._lock = threading.Lock()
        self._q = queue.Queue()
        self.subs = []
        key = None
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                key = serialization.load_pem_private_key(d["vapid_key"].encode(), None)
                self.subs = [s for s in d.get("subs", []) if valid_endpoint(s.get("endpoint"))]
            except (OSError, ValueError, KeyError, TypeError):
                pass
        self.key = key or ec.generate_private_key(ec.SECP256R1())
        if key is None:
            self._save()   # 키가 바뀌면 예전 키로 구독한 휴대폰은 못 받는다 → 휴대폰 페이지가 키를 비교해 다시 구독
        if path:
            logger.info(f"휴대폰 알림 구독 {len(self.subs)}대{' (서명 키 새로 만듦)' if key is None else ''}")
        threading.Thread(target=self._worker, name="push-sender", daemon=True).start()

    @property
    def public_key(self):
        return _b64(_point(self.key.public_key()))

    def _save(self):
        if not self.path:
            return
        pem = self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()).decode()
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"vapid_key": pem, "subs": self.subs}, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"푸시 구독 저장 실패: {e}")

    # ── 원격 서버(/api/push)에서 부르는 것 ────────────────────
    def upsert(self, sub, prefs, origin):
        """구독 추가·변경. 알림 종류를 모두 끄면 구독 삭제. 문제 있으면 오류 문구"""
        try:
            endpoint, keys = str(sub["endpoint"]), sub["keys"]
            p256dh, auth = str(keys["p256dh"]), str(keys["auth"])
            if not valid_endpoint(endpoint) or len(_unb64(p256dh)) != 65 or len(_unb64(auth)) != 16:
                raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError):
            return "잘못된 구독 정보"
        on = {k: bool(prefs.get(k)) for k in KINDS}
        with self._lock:
            self.subs = [s for s in self.subs if s["endpoint"] != endpoint]
            if any(on.values()):
                self.subs.append({"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}, **on,
                                  "origin": origin, "added": time.strftime("%Y-%m-%d %H:%M")})
                self.subs = self.subs[-MAX_SUBS:]
            self._save()
        logger.info(f"휴대폰 알림 구독 {'변경' if any(on.values()) else '해제'}: {on} (총 {len(self.subs)}대)")
        return None

    def prefs(self, endpoint):
        with self._lock:
            s = next((s for s in self.subs if s["endpoint"] == endpoint), None)
        return {k: s[k] for k in KINDS} if s else None

    # ── 알림 보내기 (장비 스레드에서 호출 — 큐에 넣기만 하고 바로 돌아감) ──
    def send(self, kind, title, body, tag=None, endpoint=None):
        """kind: alarm/done(구독에서 켠 기기만) 또는 test(endpoint 한 대). 📡가 꺼져 있으면 보내지 않음"""
        if kind != "test" and not self.enabled():
            return
        self._q.put((kind, json.dumps({"title": title, "body": body, "tag": tag or kind}, ensure_ascii=False), endpoint))

    def _worker(self):
        while True:
            kind, payload, endpoint = self._q.get()
            with self._lock:
                targets = [s for s in self.subs if (s["endpoint"] == endpoint if kind == "test" else s.get(kind))]
            if not targets:
                logger.info(f"푸시 보낼 휴대폰 없음 ({kind})")
            for s in targets:
                try:
                    self._post(s, kind, payload.encode("utf-8"))
                except Exception as e:   # 어떤 오류든 이 스레드가 죽으면 이후 알림이 전부 멈추므로 기록만 하고 계속
                    logger.error(f"푸시 전송 중 오류 ({kind}): {e}", exc_info=True)

    def _vapid(self, endpoint, origin):
        u = urlsplit(endpoint)
        head = _b64(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
        # sub는 연락처(mailto:/https:) — 애플은 형식이 틀리면 거부하므로 휴대폰이 접속한 https 주소를 쓴다
        claims = _b64(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600,
                                  "sub": origin if str(origin).startswith("https://") else "mailto:cnc-watcher@example.com"}).encode())
        r, s = decode_dss_signature(self.key.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
        sig = _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        return f"vapid t={head}.{claims}.{sig}, k={self.public_key}"

    def _post(self, s, kind, payload):
        host = urlsplit(s["endpoint"]).hostname
        req = urllib.request.Request(s["endpoint"], data=encrypt(payload, s["keys"]["p256dh"], s["keys"]["auth"]),
                                     method="POST", headers={
            "Authorization": self._vapid(s["endpoint"], s.get("origin")), "TTL": str(TTL_SEC),
            "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "Urgency": "high"})
        try:
            urllib.request.urlopen(req, timeout=10, context=SSL_CTX).close()
            logger.info(f"푸시 전송 ({kind} → {host})")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):   # 휴대폰에서 알림을 끄거나 앱을 지움 → 구독 정리
                with self._lock:
                    self.subs = [x for x in self.subs if x["endpoint"] != s["endpoint"]]
                    self._save()
                logger.info("만료된 휴대폰 알림 구독 삭제")
            else:
                logger.warning(f"푸시 전송 실패 {e.code}: {e.read()[:200]!r}")
        except OSError as e:
            logger.warning(f"푸시 전송 실패: {e}")
