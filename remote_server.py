import os
import re
import csv
import json
import time
import ctypes
import socket
import logging
import datetime
import threading
from urllib.parse import urlsplit, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from remote_page import INDEX_HTML, MANIFEST

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8765
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")   # 날짜 파라미터 검증 (경로 조작 방지)

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


class RemoteServer:
    """[v2.4] 원격 모니터링용 읽기 전용 HTTP 서버.
    FOCAS 핸들은 만든 스레드(메인)에서만 유효하므로 서버 스레드는 장비에 직접 접근하지 않고,
    메인 루프가 update_snapshot()으로 넘겨준 최신 상태와 logs/ CSV 이력만 응답한다."""

    def __init__(self, port=DEFAULT_PORT, host="0.0.0.0", log_dir=None, icons=None):
        self.port = port
        self.host = host
        self.log_dir = log_dir      # 가공/알람 이력 CSV 폴더 (notifier와 동일)
        self.icons = icons or {}    # {192: png bytes, 512: png bytes} 홈 화면 아이콘
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
                if path in ("/", "/index.html"):
                    self._send(200, "text/html; charset=utf-8", INDEX_HTML.encode("utf-8"))
                elif path == "/api/status":
                    self._json(server._status_json())
                elif path == "/api/history":
                    self._json(server._history_json(query))
                elif path == "/api/alarms":
                    self._json(server._alarms_json(query))
                elif path == "/manifest.webmanifest":
                    self._send(200, "application/manifest+json", MANIFEST.encode("utf-8"))
                elif path in ("/icon-192.png", "/icon-512.png") and int(path[6:9]) in server.icons:
                    self._send(200, "image/png", server.icons[int(path[6:9])])
                else:
                    self._send(404, "text/plain; charset=utf-8", b"not found")

            def _json(self, data):
                self._send(200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False).encode("utf-8"))

            def _send(self, code, ctype, body):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
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
