import json
import time
import ctypes
import socket
import logging
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

DEFAULT_PORT = 8765

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
    메인 루프가 update_snapshot()으로 넘겨준 최신 상태만 응답한다."""

    def __init__(self, port=DEFAULT_PORT, host="0.0.0.0"):
        self.port = port
        self.host = host
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
        return json.dumps(data, ensure_ascii=False).encode("utf-8")

    def start(self):
        if self.running:
            return
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path in ("/", "/index.html"):
                    self._send(200, "text/html; charset=utf-8", INDEX_HTML.encode("utf-8"))
                elif path == "/api/status":
                    self._send(200, "application/json; charset=utf-8", server._status_json())
                else:
                    self._send(404, "text/plain; charset=utf-8", b"not found")

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


# ── 휴대폰용 상태 페이지 (기본형, 3초마다 /api/status 갱신) ──────────
INDEX_HTML = """<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#131316">
<title>CNC Watcher</title>
<style>
  body { margin: 0; background: #131316; color: #F2F2F7; font-family: -apple-system, "Malgun Gothic", sans-serif; }
  header { display: flex; align-items: baseline; gap: 8px; padding: 18px 16px 14px; border-bottom: 1px solid #2C2C33; }
  header b { font-size: 17px; } header span { font-size: 13px; color: #636366; }
  .dot { font-size: 13px; }
  main { padding: 6px 12px; }
  .card { display: flex; background: #1C1C21; border-radius: 12px; margin: 10px 0; padding: 12px 14px 12px 8px; gap: 12px; }
  .strip { width: 5px; border-radius: 3px; }
  .body { flex: 1; min-width: 0; }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .name { font-size: 17px; font-weight: 700; }
  .badge { font-size: 12px; font-weight: 700; border-radius: 12px; padding: 4px 12px; }
  .meta { font-size: 11px; color: #636366; margin-top: 12px; }
  .meta b { font: 15px ui-monospace, Menlo, Consolas, monospace; color: #D1D1D6; margin: 0 14px 0 4px; }
  .time { font: 700 24px ui-monospace, Menlo, Consolas, monospace; margin-top: 10px; }
  .alm { display: grid; grid-template-columns: auto 1fr auto; gap: 5px 10px; font-size: 13px;
         margin-top: 10px; padding-top: 8px; border-top: 1px solid #3A1B18; }
  .alm .c { font: 700 13px ui-monospace, Menlo, Consolas, monospace; color: #FF6961; }
  .alm .m { color: #F2C9C6; overflow-wrap: anywhere; }
  .alm .t { font: 12px ui-monospace, Menlo, Consolas, monospace; color: #8E5A56; }
  footer { font-size: 12px; color: #636366; text-align: center; padding: 8px 0 24px; }
  footer.warn { color: #FFD60A; }
</style></head>
<body>
<header><span class="dot" id="dot">●</span><b id="sum">불러오는 중…</b><span id="total"></span></header>
<main id="list"></main>
<footer id="foot"></footer>
<script>
const C = { RUN:["#30D158","#0E2E1A"], ALARM:["#FF453A","#3A0E0C"], HOLD:["#FFD60A","#332B08"],
            IDLE:["#98989D","#26262C"], OFFLINE:["#5A5A60","#222226"] };
const BADGE = { RUN:"● RUN", ALARM:"▲ ALARM", HOLD:"HOLD", OFFLINE:"OFFLINE" };
const badge = m => m.state === "ALARM" && m.alarms.length > 1 ? `▲ ALARM ${m.alarms.length}` : (BADGE[m.state] || m.status);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function render(d) {
  const s = d.summary;
  document.getElementById("dot").style.color = s.color;
  document.getElementById("sum").textContent = s.text;
  document.getElementById("total").textContent = "/ 전체 " + s.total + "대";
  document.getElementById("list").innerHTML = d.machines.map(m => {
    const [fg, bg] = C[m.state] || C.IDLE, on = m.connected;
    return `<div class="card"><div class="strip" style="background:${fg}"></div><div class="body">
      <div class="row"><span class="name">${esc(m.name)}</span>
        <span class="badge" style="color:${fg};background:${bg}">${esc(badge(m))}</span></div>
      <div class="meta">MODE<b>${on ? esc(m.mode) : "-"}</b>TOOL<b>${on ? esc(m.tool) : "-"}</b>NEXT<b>${on ? esc(m.next_tool) : "-"}</b></div>
      <div class="time" style="color:${m.state === "ALARM" ? fg : (on ? "#F2F2F7" : "#636366")}">${on ? esc(m.cycle_time) : "-"}</div>
      ${m.state === "ALARM" && m.alarms.length ? `<div class="alm">${m.alarms.map(a =>
        `<span class="c">${esc(a.code)}</span><span class="m">${esc(a.msg)}</span><span class="t">${esc(a.since)}</span>`).join("")}</div>` : ""}
    </div></div>`;
  }).join("");
  const foot = document.getElementById("foot");
  foot.className = d.age_sec > 15 ? "warn" : "";
  foot.textContent = d.age_sec > 15 ? `PC 프로그램이 ${Math.round(d.age_sec)}초째 응답 없음` : "마지막 갱신 " + d.updated;
}

async function tick() {
  try {
    const r = await fetch("/api/status", { cache: "no-store" });
    render(await r.json());
  } catch (e) {
    const foot = document.getElementById("foot");
    foot.className = "warn"; foot.textContent = "PC에 연결할 수 없음 (원격 모니터링 꺼짐 또는 네트워크 문제)";
  }
}
tick(); setInterval(tick, 3000);
</script>
</body></html>
"""
