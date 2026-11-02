"""[v3.2] PC 화면(WebView2)이 죽어도 저절로 되살린다 — 속이 빈 까만 창 문제 (31번).
WebView2 메인 프로세스가 사라지면 창은 배경색(#131316)만 남고 화면 갱신도 멈춘다. 앱을 다시 켜야 돌아왔다.
앱을 다시 켜면 진행 중인 가공 기록의 시작 시각이 틀어지므로(25번), 장비 스레드는 그대로 두고 화면만 다시 만든다.

알아채는 길 세 가지:
  1. WebView2의 ProcessFailed 이벤트 (메인·화면 프로세스 종료 — 바로 안다)
  2. 화면이 상태 조회(Api.status)를 멈춤 (창이 숨겨져 있으면 타이머가 1분까지 느려지므로 넉넉히 기다린다)
  3. 창이 맨 앞에 보이는데 내용이 한 가지 색뿐"""
import shutil
import ctypes
import logging
import tempfile
import threading
import time
from PIL import ImageGrab

logger = logging.getLogger(__name__)

TICK_SEC = 2
FIRST_LOAD_SEC = 60        # 페이지가 처음 뜰 때까지 기다리는 시간 (부팅 직후엔 오래 걸릴 수 있다)
STALE_VISIBLE_SEC = 15     # 창이 보일 때: 0.5초마다 조회하므로 이만큼 없으면 멈춘 것
STALE_HIDDEN_SEC = 150     # 숨겨져 있을 때: 크롬 계열은 숨은 페이지의 타이머를 1분에 한 번까지 늦춘다
BLANK_RATIO = 0.995        # 창 안쪽이 이 비율 넘게 한 가지 색이면 그려지지 않은 것 (정상 화면은 글자·카드가 있어 60% 안팎)
BLANK_MARGIN = 10          # 둥근 모서리·테두리는 빼고 잰다
MAX_REBUILDS = 5          # 다시 만들어도 안 되는 상황이면 무한 반복하지 않는다 (사용자가 앱을 다시 켜면 초기화)
FATAL_KINDS = ("BrowserProcessExited", "RenderProcessExited")

_user32 = ctypes.WinDLL("user32")
_user32.GetForegroundWindow.restype = ctypes.c_void_p
_user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
_user32.IsIconic.argtypes = [ctypes.c_void_p]
_user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p]


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class ScreenGuard(threading.Thread):
    def __init__(self, app):
        super().__init__(name="screen-guard", daemon=True)
        self.app = app
        self.started_at = time.monotonic()
        self.last_poll = None      # 화면이 마지막으로 상태를 조회한 시각 (아직 한 번도 안 했으면 None)
        self.failed = None         # ProcessFailed가 알려 준 사유 (다음 점검 때 처리)
        self.rebuilds = 0
        self._hooked = None        # ProcessFailed를 건 EdgeChrome (다시 만들면 새로 건다)

    # ── 화면 쪽에서 불리는 것 ───────────────────────────────
    def touch(self):
        if self.last_poll is None:
            logger.info(f"화면 준비 완료 ({time.monotonic() - self.started_at:.1f}초)")
        self.last_poll = time.monotonic()

    def on_loaded(self):
        """페이지를 불러올 때마다 (pywebview events.loaded). WebView2 객체는 화면 스레드에서만 만질 수 있다."""
        try:
            self._invoke(self._hook)
        except Exception as e:
            logger.warning(f"화면 이벤트 연결 실패: {e}")

    def _invoke(self, fn):
        from System import Func, Type
        self.app.window.native.Invoke(Func[Type](fn))

    def _hook(self):
        browser = self.app.window.native.browser
        if browser is self._hooked:
            return
        self._hooked = browser
        core = browser.webview.CoreWebView2
        core.ProcessFailed += self._on_process_failed
        logger.info(f"WebView2 {core.Environment.BrowserVersionString} (프로세스 {core.BrowserProcessId})")

    def _on_process_failed(self, sender, args):
        kind = str(args.ProcessFailedKind)
        logger.warning(f"화면 프로세스 문제: {kind} (사유 {args.Reason}, 종료 코드 {args.ExitCode})")
        if kind in FATAL_KINDS:
            self.failed = kind

    # ── 점검 ───────────────────────────────────────────────
    def _visible(self):
        h = self.app.hwnd
        return bool(h) and bool(_user32.IsWindowVisible(h)) and not _user32.IsIconic(h)

    def _blank(self):
        """창이 맨 앞에 보일 때만 실제 화면을 찍어 본다. 가려져 있거나 잠금 화면이면 다른 것이 찍히므로 재지 않는다."""
        h = self.app.hwnd
        if not self._visible() or _user32.GetForegroundWindow() != h:
            return None
        rc = _RECT()
        _user32.GetWindowRect(h, ctypes.byref(rc))
        box = (rc.left + BLANK_MARGIN, rc.top + BLANK_MARGIN, rc.right - BLANK_MARGIN, rc.bottom - BLANK_MARGIN)
        if box[2] <= box[0] or box[3] <= box[1]:
            return None
        try:
            img = ImageGrab.grab(box, all_screens=True).convert("RGB")
        except OSError:
            return None   # 원격 데스크톱이 끊겼을 때 등
        n, color = max(img.getcolors(img.width * img.height), key=lambda c: c[0])
        ratio = n / (img.width * img.height)
        return f"단색 #{color[0]:02X}{color[1]:02X}{color[2]:02X} {ratio:.1%}" if ratio >= BLANK_RATIO else None

    def _stale(self):
        """프로세스 종료를 알리거나 조회가 멈췄으면 그 사유, 아니면 None"""
        if self.failed:
            return f"프로세스 종료 ({self.failed})"
        now = time.monotonic()
        if self.last_poll is None:
            return f"화면이 {FIRST_LOAD_SEC}초 안에 뜨지 않음" if now - self.started_at > FIRST_LOAD_SEC else None
        limit = STALE_VISIBLE_SEC if self._visible() else STALE_HIDDEN_SEC
        return f"화면이 {now - self.last_poll:.0f}초째 응답 없음" if now - self.last_poll > limit else None

    def run(self):
        last_tick, tick, hits, blank = time.monotonic(), 0, 0, None
        while not self.app.quitting:
            time.sleep(TICK_SEC)
            now = time.monotonic()
            if now - last_tick > TICK_SEC * 10:   # 절전에서 돌아옴 — 그동안은 조회가 없는 게 정상이니 기준을 다시 잡는다
                self.started_at = now
                if self.last_poll is not None:
                    self.last_poll = now
            last_tick = now
            tick += 1
            if tick % 2 == 0:   # 화면 찍기는 4초에 한 번, 두 번 연속일 때만 믿는다
                blank = self._blank()
                hits = hits + 1 if blank else 0
            why = self._stale() or (blank if hits >= 2 else None)
            if not why or self.app.quitting:
                continue
            if self.rebuilds >= MAX_REBUILDS:
                logger.error(f"화면을 {MAX_REBUILDS}번 다시 만들어도 복구되지 않음 — 앱을 다시 켜 주세요 ({why})")
                return
            hits, blank = 0, None
            self._rebuild(why)

    # ── 다시 만들기 ─────────────────────────────────────────
    def _rebuild(self, why):
        self.rebuilds += 1
        logger.warning(f"화면 다시 만드는 중 ({self.rebuilds}/{MAX_REBUILDS}): {why}")
        self.failed, self.last_poll = None, None
        self.started_at = time.monotonic()
        app, old_dir = self.app, None
        from webview.platforms import winforms
        # 새 화면은 일반 크기로 시작하므로 파이썬 쪽 최소화 모드도 맞춘다
        app.compact = False
        app.set_topmost(False)

        def swap():
            nonlocal old_dir
            form = app.window.native
            old = form.browser
            old_dir = old.user_data_folder
            form.Controls.Remove(old.webview)
            try:
                old.webview.Dispose()
            except Exception as e:
                logger.warning(f"이전 화면 정리 실패: {e}")
            # 이전 프로세스가 아직 끝나는 중일 수 있어 같은 폴더를 쓰지 않는다 (private_mode라 지켜야 할 내용도 없음)
            form.browser = winforms.Chromium.EdgeChrome(form, app.window, tempfile.mkdtemp(prefix="pywebview_"))
            form.webview = form.browser.webview
            form.webview.Focus()
        try:
            self._invoke(swap)
        except Exception as e:
            logger.error(f"화면 다시 만들기 실패: {e}", exc_info=True)
            return
        if old_dir:
            threading.Timer(10, shutil.rmtree, (old_dir,), {"ignore_errors": True}).start()
