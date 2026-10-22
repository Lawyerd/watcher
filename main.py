import io
import os
import sys
import json
import time
import base64
import ctypes
import socket
import logging
import tempfile
import threading
import winsound
from logging.handlers import RotatingFileHandler
from PIL import Image, ImageDraw
import pystray
import webview

VERSION = "v3.0"
# 자가 테스트: 실행 중인 앱과 함께 돌 수 있게 중복 실행 검사 생략, 이력은 임시 폴더, 토스트 끔
SELFTEST = "--selftest" in sys.argv

_handlers = [RotatingFileHandler("cnc_watcher.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")]
if sys.stderr:   # exe(--windowed)에서는 stderr가 없다
    _handlers.append(logging.StreamHandler())
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", handlers=_handlers)
logger = logging.getLogger(__name__)

_lock_socket = None
def is_already_running():
    global _lock_socket
    try:
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_socket.bind(("127.0.0.1", 54321))
        return False
    except socket.error:
        return True

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    WEB_DIR  = os.path.join(sys._MEIPASS, "web")      # [v3.0] 화면 파일은 exe 안에 묶음
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    WEB_DIR  = os.path.join(BASE_DIR, "web")

DLL_DIR      = os.path.join(BASE_DIR, "dll")
CONFIG_FILE  = os.path.join(BASE_DIR, "machines.json")
REMOTE_FILE  = os.path.join(BASE_DIR, "remote.json")    # [v2.4] 원격 PIN 해시·로그인 서명 키
DLL_PATH     = os.path.join(DLL_DIR, "Fwlib64.dll")
ICONS_DIR    = os.path.join(BASE_DIR, "icons")
ICON_PATH    = os.path.join(ICONS_DIR, "watcher_icon.ico")
ICON_PNG     = os.path.join(ICONS_DIR, "watcher_icon.png")   # 토스트 알림용 (winotify는 png 필요)
FONTS_DIR    = os.path.join(BASE_DIR, "fonts")

if os.path.exists(DLL_DIR):
    if hasattr(os, 'add_dll_directory'): os.add_dll_directory(DLL_DIR)
    os.environ['PATH'] = DLL_DIR + os.pathsep + os.environ['PATH']

# DLL 경로 설정 뒤에 import (fanuc_logic이 Fwlib을 찾을 수 있도록)
from notifier import StatusNotifier                                          # noqa: E402
from utilization import UtilizationTracker                                   # noqa: E402
from remote_server import RemoteServer, RemoteAuth, PIN_LEN, local_urls, funnel_url   # noqa: E402
from poller import Poller                                                    # noqa: E402

WIDTH, COMPACT_WIDTH = 640, 240
_user32 = ctypes.WinDLL("user32")
_user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_ASYNCWINDOWPOS = 0x1, 0x2, 0x10, 0x4000


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def draw_watcher_icon(px=512):
    """[v2.3] 펄스 라인 아이콘: 다크 라운드 사각형 + 초록 심박 라인 (512px 렌더 후 축소)"""
    img = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = px / 64
    d.rounded_rectangle((2 * s, 2 * s, 62 * s, 62 * s), radius=14 * s, fill="#1C1C21")
    pts = [(8, 32), (20, 32), (26, 16), (34, 48), (40, 32), (56, 32)]
    pts = [(x * s, y * s) for x, y in pts]
    w = int(5 * s)
    d.line(pts, fill="#30D158", width=w, joint="curve")
    r = w / 2  # 라인 양 끝을 둥글게
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill="#30D158")
    return img


def ensure_icons():
    os.makedirs(ICONS_DIR, exist_ok=True)
    try:
        if not os.path.exists(ICON_PATH):
            draw_watcher_icon().save(ICON_PATH, format='ICO', sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
        if not os.path.exists(ICON_PNG):   # 토스트용 고해상도 PNG (256px)
            draw_watcher_icon().resize((256, 256), Image.LANCZOS).save(ICON_PNG, format='PNG')
    except Exception as e:
        logger.error(f"아이콘 생성 실패: {e}")


def web_icons():
    """휴대폰 홈 화면 아이콘용 PNG (192/512px)"""
    icons, img = {}, draw_watcher_icon()
    for px in (192, 512):
        buf = io.BytesIO()
        img.resize((px, px), Image.LANCZOS).save(buf, format="PNG")
        icons[px] = buf.getvalue()
    return icons


def load_configs():
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"설정 로드 실패: {e}")
        return []


def build_html():
    """PC 화면 HTML. 동봉 폰트(JetBrains Mono)를 base64로 넣는다 — 웹 화면 엔진은 별도 프로세스라
    파이썬 프로세스에 등록한 폰트(AddFontResourceEx)를 못 쓰고, html 문자열로 띄우므로 파일 경로도 못 쓴다."""
    with open(os.path.join(WEB_DIR, "desktop.html"), encoding="utf-8") as f:
        html = f.read()
    faces = []
    for name, weight in (("JetBrainsMono-Regular.ttf", 400), ("JetBrainsMono-Bold.ttf", 700)):
        try:
            with open(os.path.join(FONTS_DIR, name), "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            faces.append(f'@font-face {{ font-family: "JetBrains Mono"; font-weight: {weight}; '
                         f'src: url(data:font/ttf;base64,{data}) format("truetype"); }}')
        except OSError:
            pass   # 폰트가 없으면 CSS의 대체 글꼴(Cascadia Mono → Consolas) 사용
    return html.replace("/*@FONTS@*/", "\n".join(faces)).replace("@VERSION@", VERSION)


def validate_machines(rows):
    """설정 창 입력 검증. 문제 있으면 오류 문구, 정상이면 정리된 목록"""
    out, seen = [], set()
    for r in rows:
        name, ip, port = str(r.get("name", "")).strip(), str(r.get("ip", "")).strip(), str(r.get("port", "")).strip()
        if not name or not ip:
            return "장비명과 IP 주소를 모두 입력해 주세요."
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            return f"[{name}] 포트는 1~65535 사이의 숫자여야 합니다."
        if ip in seen:
            return f"IP 주소가 중복되었습니다: {ip}"
        seen.add(ip)
        out.append({"name": name, "ip": ip, "port": int(port)})
    return out if out else "최소 1대 이상의 장비가 필요합니다."


class Api:
    """[v3.0] PC 화면(JS) → 파이썬 호출 창구 (pywebview js_api).
    HTTP가 아니라 창 내부 연결이라 Funnel로 공개되는 원격 서버와 완전히 분리된다 — 연결·설정 같은
    제어 기능은 절대 웹 서버로 열지 말 것. 각 호출은 별도 스레드에서 실행되므로 FOCAS는 직접 부르지 않고
    poller에 명령만 넣는다. (밑줄로 시작하는 속성은 pywebview가 화면 쪽에 내보내지 않는다)"""

    def __init__(self, app):
        self._app = app

    # ── 상태 ─────────────────────────────────────────────
    def init(self):
        a = self._app
        return {"version": VERSION, "notify": a.poller.notify_enabled, "pin_len": PIN_LEN, "selftest": SELFTEST}

    def status(self):
        return dict(self._app.poller.snapshot(), events=self._app.poller.pop_events())

    def connect(self, ip):
        self._app.poller.request("connect", ip)

    def disconnect(self, ip):
        self._app.poller.request("disconnect", ip)

    def set_notify(self, on):
        self._app.poller.notify_enabled = bool(on)   # 토스트만 끈다 (CSV 이력은 항상 기록)
        return self._app.poller.notify_enabled

    # ── 원격 모니터링 ─────────────────────────────────────
    def remote_toggle(self):
        a = self._app
        if a.remote.running:
            a.poller.request("remote_stop")
            return {"running": False}
        if not a.auth.has_pin:
            return {"need_pin": True}   # PIN 없이 인터넷에 공개되지 않도록 PIN부터
        a.poller.request("remote_start")
        return {"running": True}

    def remote_info(self):
        a = self._app
        return {"has_pin": a.auth.has_pin, "running": a.remote.running, "funnel": funnel_url(),
                "urls": local_urls(a.remote.port)}

    def remote_save(self, pin):
        a, pin = self._app, str(pin or "").strip()
        if pin:
            if len(pin) != PIN_LEN or not pin.isdigit():
                return {"error": f"PIN은 숫자 {PIN_LEN}자리예요"}
            a.auth.set_pin(pin)   # 기존 로그인 기기는 전부 로그아웃됨
            logger.info("원격 모니터링 PIN 변경")
        elif not a.auth.has_pin:
            return {"error": "PIN을 정해주세요"}
        if not a.remote.running:
            a.poller.request("remote_start")
        return {"ok": True}

    def remote_logout_all(self):
        self._app.auth.logout_all()
        return {"ok": True}

    # ── 장비 설정 ─────────────────────────────────────────
    def get_machines(self):
        return [{"name": m.name, "ip": m.ip, "port": m.port} for m in self._app.poller.machines]

    def save_machines(self, rows):
        result = validate_machines(rows or [])
        if isinstance(result, str):
            return {"error": result}
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=4)
        except OSError as e:
            logger.error(f"설정 저장 실패: {e}")
            return {"error": f"machines.json 저장 중 오류가 발생했습니다.\n{e}"}
        self._app.poller.request("set_machines", result)
        return {"ok": True}

    # ── 창 ───────────────────────────────────────────────
    def minimize(self):
        self._app.window.minimize()

    def hide(self):
        self._app.window.hide()   # 닫기(✕) = 트레이로 숨김, 감시는 계속

    def fit(self, height):
        """내용 높이에 맞춰 창 높이 조절 (펼칠 땐 애니메이션 전에, 접을 땐 끝난 뒤에 화면이 호출)"""
        a = self._app
        a.window.resize(COMPACT_WIDTH if a.compact else WIDTH, max(60, min(900, int(height))))

    def set_compact(self, on, height):
        """최소화(슬림) 모드: 좁은 폭 + 항상 위"""
        a = self._app
        a.compact = bool(on)
        a.set_topmost(a.compact)
        self.fit(height)

    def compact_drag(self):
        """최소화 모드 카드 끌기: 마우스 버튼을 놓을 때까지 창을 따라 움직인다.
        움직인 거리를 돌려주며, 거의 안 움직였으면 화면이 '클릭(원래 크기로)'으로 처리한다."""
        w, start, cur = self._app.window, _POINT(), _POINT()
        _user32.GetCursorPos(ctypes.byref(start))
        wx, wy, moved = w.x, w.y, 0
        while _user32.GetAsyncKeyState(0x01) & 0x8000:   # VK_LBUTTON
            _user32.GetCursorPos(ctypes.byref(cur))
            dx, dy = cur.x - start.x, cur.y - start.y
            if moved or abs(dx) > 3 or abs(dy) > 3:
                moved = max(moved, abs(dx) + abs(dy))
                w.move(wx + dx, wy + dy)
            time.sleep(0.015)
        return moved

    def attention(self):
        """알람: 숨겨져 있어도 창을 앞으로 띄우고 경고음"""
        a = self._app
        a.window.show()
        a.window.restore()
        if not a.compact:
            a.set_topmost(True)
            threading.Timer(1.5, lambda: a.set_topmost(a.compact)).start()
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)

    def report(self, text):
        """자가 테스트 결과 기록 (screenshot:이름 → 창 캡처를 임시 폴더에 저장)"""
        a = self._app
        if text.startswith("test:"):   # 창 동작 점검: 숨기기 / 트레이 '열기' / Alt+F4(WM_CLOSE) / 보이는지 기록
            act = text[5:]
            if act == "hide":
                self.hide()
            elif act == "show":
                a.show_window()
            elif act == "wmclose":
                _user32.PostMessageW(ctypes.c_void_p(a.hwnd), 0x0010, 0, 0)
            logger.info(f"[자가 테스트] {act} → 창 보임={bool(_user32.IsWindowVisible(ctypes.c_void_p(a.hwnd)))}")
            return
        if text.startswith("screenshot:"):
            from PIL import ImageGrab
            w, path = a.window, os.path.join(a.data_dir, f"selftest_{text.split(':', 1)[1]}.png")
            ImageGrab.grab((w.x, w.y, w.x + w.width, w.y + w.height), all_screens=True).save(path)
            logger.info(f"[자가 테스트] 캡처 {path}")
            return
        logger.info(f"[자가 테스트] {text}")
        if text.startswith("selftest done"):
            threading.Timer(0.5, a.quit).start()


class App:
    def __init__(self):
        ensure_icons()
        self.data_dir = tempfile.mkdtemp(prefix="cncw_selftest_") if SELFTEST else BASE_DIR
        self.notifier = StatusNotifier(icon_path=ICON_PNG, base_dir=self.data_dir)
        self.util = UtilizationTracker(self.notifier.log_dir)
        self.auth = RemoteAuth(None if SELFTEST else REMOTE_FILE)
        self.remote = RemoteServer(log_dir=self.notifier.log_dir, icons=web_icons(), auth=self.auth)
        self.poller = Poller(load_configs(), DLL_PATH, self.notifier, self.util, self.remote)
        self.poller.notify_enabled = not SELFTEST
        self.compact = False
        self.quitting = False
        self.hwnd = None   # 창이 뜬 뒤(_on_shown) 채움
        self.api = Api(self)
        self.window = webview.create_window(
            f"DN Solutions Machine Watcher {VERSION}", html=build_html(), js_api=self.api,
            width=WIDTH, height=322, frameless=True, easy_drag=False, background_color="#131316", min_size=(200, 60))
        self.window.events.shown += self._on_shown
        self.window.events.closing += self._on_closing

    def set_topmost(self, on):
        """항상 위 켜기/끄기. pywebview의 window.on_top은 다른 스레드에서 .NET 속성을 GIL을 쥔 채 바꿔
        화면 스레드와 서로 기다리는(데드락) 문제가 있어 Win32 SetWindowPos(비동기)로 직접 한다."""
        if self.hwnd:
            _user32.SetWindowPos(self.hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0,
                                 SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)

    def _on_shown(self):
        try:   # 윈도우 11 둥근 모서리 (윈도우 10에서는 무시됨)
            self.hwnd = hwnd = self.window.native.Handle.ToInt64()
            ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 33, ctypes.byref(ctypes.c_int(2)), 4)
        except Exception as e:
            logger.warning(f"둥근 모서리 적용 실패: {e}")

    def _on_closing(self):
        if not self.quitting:   # Alt+F4 등으로 닫아도 종료하지 않고 트레이로
            self.window.hide()
            return False

    def setup_tray(self):
        try:
            img = Image.open(ICON_PATH)
        except Exception:
            img = draw_watcher_icon(64)

        menu = (pystray.MenuItem('열기', lambda icon, item: self.show_window(), default=True), pystray.MenuItem('종료', lambda icon, item: self.quit()))
        self.tray = pystray.Icon("CNC Watcher", img, "CNC Watcher", menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def show_window(self):
        self.window.show()
        self.window.restore()

    def quit(self):
        self.quitting = True
        self.window.destroy()

    def run(self):
        self.poller.start()
        self.setup_tray()
        webview.start(private_mode=True)
        # 창이 닫히면 장비 스레드가 핸들을 정리하고(원격 서버 종료·가동률 마감 포함) 끝날 때까지 잠깐 기다림
        self.poller.request("shutdown")
        self.poller.join(timeout=5)
        self.tray.stop()


if __name__ == "__main__":
    if not SELFTEST and is_already_running():
        ctypes.windll.user32.MessageBoxW(None, "이미 실행 중입니다.", "CNC Watcher", 0x40)
        sys.exit(0)
    App().run()
