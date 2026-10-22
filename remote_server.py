import os
import re
import csv
import hmac
import json
import time
import ctypes
import shutil
import socket
import hashlib
import logging
import secrets
import datetime
import threading
import subprocess
from http.cookies import SimpleCookie
from urllib.parse import urlsplit, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import webui

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8765
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")   # 날짜 파라미터 검증 (경로 조작 방지)

# [v2.4] PIN 로그인 (Funnel로 인터넷에 공개되므로 모든 /api/* 요청에 로그인 필요)
PIN_LEN = 6
SESSION_DAYS = 30                 # 한 번 로그인하면 유지되는 기간
MAX_FAILS, LOCK_SEC = 5, 300      # 5번 틀리면 5분 잠금 (전체 기준)
COOKIE = "cw_session"
TAILSCALE_EXE = r"C:\Program Files\Tailscale\tailscale.exe"

# 절전 차단 (SetThreadExecutionState) — 호출한 스레드가 살아 있는 동안 유지되므로 메인 스레드에서 호출
ES_CONTINUOUS      = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def set_keep_awake(on):
    """원격 모니터링 중 PC가 절전에 들어가면 서버도 같이 죽으므로 시스템 절전만 차단 (모니터는 꺼져도 됨)"""
    try:
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
        ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags))
    except Exception as e:
        logger.error(f"절전 차단 설정 실패: {e}")


def local_urls(port):
    """휴대폰에서 접속할 수 있는 이 PC의 IPv4 주소 목록 (사내망/와이파이/Tailscale 등)"""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    ips.discard("127.0.0.1")
    return [f"http://{ip}:{port}" for ip in sorted(ips)]


def funnel_url():
    """Tailscale Funnel이 켜져 있으면 공개 주소(https://기기.tailnet.ts.net), 아니면 None.
    최대 3초 걸리므로 메인 스레드에서 직접 부르지 말 것."""
    exe = shutil.which("tailscale") or TAILSCALE_EXE
    try:
        out = subprocess.run([exe, "funnel", "status", "--json"], capture_output=True, timeout=3,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
        hosts = [h for h, on in (json.loads(out or b"{}").get("AllowFunnel") or {}).items() if on]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return "https://" + hosts[0].removesuffix(":443") if hosts else None


class RemoteAuth:
    """PIN 해시(PBKDF2)와 로그인 쿠키 서명 키를 remote.json에 보관.
    PIN을 바꾸거나 '모든 기기 로그아웃' 하면 서명 키가 바뀌어 기존 로그인이 전부 무효가 된다."""

    def __init__(self, path=None):
        self.path = path
        self.pin_salt = self.pin_hash = self.secret = None
        self._fails, self._locked_until = 0, 0.0
        self._lock = threading.Lock()
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                self.pin_salt, self.pin_hash, self.secret = d.get("pin_salt"), d.get("pin_hash"), d.get("secret")
            except (OSError, ValueError):
                pass
        self.secret = self.secret or secrets.token_hex(32)

    @property
    def has_pin(self):
        return bool(self.pin_hash)

    @staticmethod
    def _hash(pin, salt):
        return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()

    def _save(self):
        if not self.path:
            return
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"pin_salt": self.pin_salt, "pin_hash": self.pin_hash, "secret": self.secret}, f, indent=4)

    def set_pin(self, pin):
        salt = secrets.token_hex(16)
        self.pin_salt, self.pin_hash, self.secret = salt, self._hash(pin, salt), secrets.token_hex(32)
        self._save()

    def logout_all(self):
        self.secret = secrets.token_hex(32)
        self._save()

    def try_login(self, pin):
        """(성공 여부, 남은 시도 횟수, 잠금 남은 초). 형식이 틀린 PIN도 실패로 센다."""
        with self._lock:
            now = time.monotonic()
            if now < self._locked_until:
                return False, 0, int(self._locked_until - now) + 1
            if (self.has_pin and len(pin) == PIN_LEN and pin.isdigit()
                    and hmac.compare_digest(self._hash(pin, self.pin_salt), self.pin_hash)):
                self._fails = 0
                return True, MAX_FAILS, 0
            self._fails += 1
            if self._fails >= MAX_FAILS:
                self._fails, self._locked_until = 0, now + LOCK_SEC
                logger.warning(f"원격 PIN {MAX_FAILS}회 실패 → {LOCK_SEC}초 잠금")
                return False, 0, LOCK_SEC
            return False, MAX_FAILS - self._fails, 0

    def _sign(self, exp):
        return hmac.new(self.secret.encode(), exp.encode(), hashlib.sha256).hexdigest()

    def make_token(self):
        exp = str(int(time.time()) + SESSION_DAYS * 86400)
        return f"{exp}.{self._sign(exp)}"

    def valid_token(self, token):
        exp, _, sig = token.partition(".")
        return exp.isdigit() and int(exp) > time.time() and hmac.compare_digest(sig, self._sign(exp))


class RemoteServer:
    """[v2.4] 원격 모니터링용 읽기 전용 HTTP 서버.
    FOCAS 핸들은 만든 스레드(메인)에서만 유효하므로 서버 스레드는 장비에 직접 접근하지 않고,
    메인 루프가 update_snapshot()으로 넘겨준 최신 상태와 logs/ CSV 이력만 응답한다."""

    def __init__(self, port=DEFAULT_PORT, host="0.0.0.0", log_dir=None, icons=None, auth=None):
        self.port = port
        self.host = host
        self.log_dir = log_dir      # 가공/알람 이력 CSV 폴더 (notifier와 동일)
        self.icons = icons or {}    # {192: png bytes, 512: png bytes} 홈 화면 아이콘
        self.auth = auth or RemoteAuth()
        # 휴대폰 페이지 (web/phone.html + 공통 팔레트·도우미) — 시작할 때 한 번 만들어 둔다
        self.page = webui.page("phone.html").encode("utf-8")
        self.manifest = webui.read("manifest.webmanifest").encode("utf-8")
        self._httpd = None
        self._lock = threading.Lock()
        self._snapshot = {"summary": {}, "machines": []}
        self._snapshot_at = time.monotonic()

    @property
    def running(self):
        return self._httpd is not None

    def update_snapshot(self, snapshot):
        with self._lock:
            self._snapshot = snapshot
            self._snapshot_at = time.monotonic()

    def _status_json(self):
        with self._lock:
            data = dict(self._snapshot)
            # 메인 루프가 멈추면 값이 갱신되지 않으므로 경과 시간을 함께 내려준다
            data["age_sec"] = round(time.monotonic() - self._snapshot_at, 1)
        return data

    def _log_rows(self, prefix, query):
        """logs/{prefix}_{날짜}.csv 행 목록 (헤더 제외). 날짜는 ?date=YYYY-MM-DD, 기본 오늘"""
        today = datetime.date.today().isoformat()
        date = query.get("date", [today])[0]
        if not DATE_RE.match(date):
            date = today
        rows = []
        if self.log_dir:
            try:
                with open(os.path.join(self.log_dir, f"{prefix}_{date}.csv"), newline="", encoding="utf-8-sig") as f:
                    rows = list(csv.reader(f))[1:]
            except OSError:
                pass   # 그 날 기록 없음
        return {"date": date, "today": today}, rows

    def _history_json(self, query):
        data, rows = self._log_rows("history", query)
        data["rows"] = [{"machine": r[1], "start": r[2], "end": r[3], "cycle": r[4]}
                        for r in reversed(rows) if len(r) >= 5]
        return data

    def _alarms_json(self, query):
        data, rows = self._log_rows("alarm", query)
        data["rows"] = [{"time": r[1], "machine": r[2], "kind": r[3], "code": r[4], "msg": r[5]}
                        for r in reversed(rows) if len(r) >= 6]
        return data

    def start(self):
        if self.running:
            return
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                url = urlsplit(self.path)
                path, query = url.path, parse_qs(url.query)
                # 페이지·아이콘은 공개 (로그인 화면을 띄워야 하므로), 데이터(/api/*)는 로그인 필요
                if path in ("/", "/index.html"):
                    self._send(200, "text/html; charset=utf-8", server.page)
                elif path == "/manifest.webmanifest":
                    self._send(200, "application/manifest+json", server.manifest)
                elif path in ("/icon-192.png", "/icon-512.png") and int(path[6:9]) in server.icons:
                    self._send(200, "image/png", server.icons[int(path[6:9])])
                elif path.startswith("/api/") and not self._authed():
                    self._json({"error": "login"}, 401)
                elif path == "/api/status":
                    self._json(server._status_json())
                elif path == "/api/history":
                    self._json(server._history_json(query))
                elif path == "/api/alarms":
                    self._json(server._alarms_json(query))
                else:
                    self._send(404, "text/plain; charset=utf-8", b"not found")

            def do_POST(self):
                if urlsplit(self.path).path != "/api/login":
                    return self._send(404, "text/plain; charset=utf-8", b"not found")
                length = int(self.headers.get("Content-Length") or 0)
                if length > 1024:
                    return self._send(413, "text/plain; charset=utf-8", b"too large")
                try:
                    pin = str(json.loads(self.rfile.read(length) or b"{}").get("pin", ""))
                except (ValueError, AttributeError):
                    pin = ""
                ok, left, locked = server.auth.try_login(pin)
                if not ok:
                    return self._json({"ok": False, "left": left, "locked_sec": locked}, 429 if locked else 401)
                # Funnel(https)로 들어온 경우에만 Secure — 사내망 http 접속에서도 로그인되도록
                secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                cookie = (f"{COOKIE}={server.auth.make_token()}; Max-Age={SESSION_DAYS * 86400}; "
                          f"Path=/; HttpOnly; SameSite=Strict{secure}")
                self._json({"ok": True}, headers=[("Set-Cookie", cookie)])

            def _authed(self):
                c = SimpleCookie()
                try:
                    c.load(self.headers.get("Cookie", ""))
                except Exception:
                    return False
                return server.auth.has_pin and COOKIE in c and server.auth.valid_token(c[COOKIE].value)

            def _json(self, data, code=200, headers=()):
                self._send(code, "application/json; charset=utf-8",
                           json.dumps(data, ensure_ascii=False).encode("utf-8"), headers)

            def _send(self, code, ctype, body, headers=()):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                for k, v in headers:
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                # exe(--noconsole)에서는 sys.stderr가 None이라 기본 구현이 예외를 낸다
                logger.debug("%s - %s", self.address_string(), fmt % args)

        httpd = ThreadingHTTPServer((self.host, self.port), Handler)   # 포트 사용 중이면 OSError
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self._httpd = httpd
        set_keep_awake(True)
        logger.info(f"원격 모니터링 시작: {local_urls(self.port)}")

    def stop(self):
        httpd, self._httpd = self._httpd, None
        if httpd is None:
            return
        set_keep_awake(False)

        # shutdown()은 serve_forever 루프가 끝날 때까지 블록되므로 UI가 멈추지 않게 별도 스레드에서
        def _close():
            httpd.shutdown()
            httpd.server_close()
        threading.Thread(target=_close, daemon=True).start()
        logger.info("원격 모니터링 종료")
