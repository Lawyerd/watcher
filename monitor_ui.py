import os
import time
import ctypes
import datetime
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk
from remote_server import PIN_LEN

# ── [v2.3] A안 다크 테마 팔레트 ──────────────────────────────
COL_BG       = "#131316"   # 창 배경
COL_CARD     = "#1C1C21"   # 카드 배경
COL_BORDER   = "#2C2C33"   # 테두리/구분선
COL_TEXT     = "#F2F2F7"   # 주요 텍스트
COL_VALUE    = "#D1D1D6"   # 값 텍스트
COL_MUTED    = "#8E8E93"   # 보조 텍스트
COL_SUB      = "#636366"   # 흐린 라벨
COL_BTN      = "#26262C"   # 어두운 버튼
COL_BTN_HOV  = "#33333A"
COL_ACCENT   = "#0A84FF"   # 강조(연결/저장)
COL_ACCENT_HOV = "#0B6FD6"
COL_CLOSE_HOV  = "#C42B1C"   # [v2.4] 닫기 버튼 호버 (Windows 표준 빨강)
COL_ON_BG      = "#0E2E1A"   # [v2.4] 켜진 토글 버튼(📡 원격·🔔 알림) 배경
COL_ALM_CODE   = "#FF6961"   # [v2.4] 알람 목록: 번호
COL_ALM_MSG    = "#F2C9C6"   #        내용
COL_ALM_SUB    = "#8E5A56"   #        발생 시각
COL_ALM_LINE   = "#3A1B18"   #        구분선
COL_OUTLINE    = "#3A3A42"   # [v2.4] 테두리 버튼 (연결 해제 상태)

# [v2.4] 헤더 아이콘 글리프 (Segoe Fluent Icons / MDL2 Assets 공통 코드)
ICON_SETTINGS = ""
ICON_BELL     = ""
ICON_BELL_OFF = ""
ICON_COMPACT  = ""
ICON_REMOTE   = ""
ICON_MINIMIZE = ""
ICON_CLOSE    = ""
ICON_CHEV_DN  = ""   # 카드 펼치기
ICON_CHEV_UP  = ""   # 카드 접기
ICON_PLUG     = ""   # 연결 버튼 (Segoe Fluent Icons에만 있음 → 이미지로 그려 글자 옆에 붙임)

# [v2.4] 패널 펼치기/접기 애니메이션
ANIM_MS, ANIM_STEP_MS = 200, 15
SWAP_DELAY_MS = 150   # 펼침이 끝난 뒤 실제 패널이 다 그려질 때까지 스냅샷을 덮어 두는 시간

# [v2.4] 부하 막대: 0~150% 눈금, 80% 이상 노랑 · 100% 이상 빨강
LOAD_SCALE = 150

def glyph_image(glyph, color, px=14):
    """아이콘 폰트 글리프를 CTkImage로 만든다 (CTkButton은 글꼴이 하나라 아이콘+글자를 함께 쓰려면 이미지 필요)"""
    try:
        font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "SegoeIcons.ttf"), px * 2)
    except OSError:
        return None   # Win10처럼 Fluent 아이콘 폰트가 없으면 글자만 표시
    img = Image.new("RGBA", (px * 2, px * 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((px, px), glyph, font=font, fill=color, anchor="mm")
    return ctk.CTkImage(light_image=img, dark_image=img, size=(px, px))

def load_color(pct):
    if pct is None:   return COL_SUB
    if pct >= 100:    return STATE_COLORS["ALARM"][0]
    if pct >= 80:     return STATE_COLORS["HOLD"][0]
    return STATE_COLORS["RUN"][0]

# Win32 상수 (테두리 없는 창을 작업표시줄에 표시/최소화하기 위함)
GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_MINIMIZEBOX   = 0x00020000
WS_EX_APPWINDOW  = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SW_MINIMIZE = 6
DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2
DWMWA_BORDER_COLOR = 34

# pystray 등과 함수 객체(argtypes)를 공유하지 않도록 별도 인스턴스로 로드
_user32 = ctypes.WinDLL("user32")
_user32.GetParent.restype = ctypes.c_void_p
_user32.GetParent.argtypes = [ctypes.c_void_p]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
_user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
_user32.RedrawWindow.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
RDW_INVALIDATE, RDW_ERASE = 0x1, 0x4
_user32.GetDC.restype = ctypes.c_void_p
_user32.GetDC.argtypes = [ctypes.c_void_p]
_user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

_gdi32 = ctypes.WinDLL("gdi32")
for _name, _res, _args in (
        ("CreateCompatibleDC", ctypes.c_void_p, [ctypes.c_void_p]),
        ("CreateCompatibleBitmap", ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]),
        ("SelectObject", ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_void_p]),
        ("DeleteObject", ctypes.c_int, [ctypes.c_void_p]),
        ("DeleteDC", ctypes.c_int, [ctypes.c_void_p]),
        ("BitBlt", ctypes.c_int, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint]),
        ("GetDIBits", ctypes.c_int, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                                     ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint])):
    getattr(_gdi32, _name).restype, getattr(_gdi32, _name).argtypes = _res, _args

class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]

def capture_screen(x, y, width, height):
    """화면의 (x, y, w, h) 영역을 PIL 이미지로 — 보이는 그대로 복사(BitBlt)라 수 ms면 끝남.
    (PrintWindow는 창 전체를 다시 그려 ~100ms, PIL ImageGrab은 모니터 전체를 찍고 잘라 ~40ms)"""
    sdc = _user32.GetDC(None)
    mdc = _gdi32.CreateCompatibleDC(sdc)
    bmp = _gdi32.CreateCompatibleBitmap(sdc, width, height)
    old = _gdi32.SelectObject(mdc, bmp)
    try:
        _gdi32.BitBlt(mdc, 0, 0, width, height, sdc, x, y, 0x00CC0020)   # SRCCOPY
        bi = _BITMAPINFOHEADER(ctypes.sizeof(_BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(width * height * 4)
        _gdi32.GetDIBits(mdc, bmp, 0, height, buf, ctypes.byref(bi), 0)
        return Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB")
    finally:
        _gdi32.SelectObject(mdc, old)
        _gdi32.DeleteObject(bmp)
        _gdi32.DeleteDC(mdc)
        _user32.ReleaseDC(None, sdc)

# 상태별 (강조색, 배지 배경)
STATE_COLORS = {
    "RUN":     ("#30D158", "#0E2E1A"),
    "ALARM":   ("#FF453A", "#3A0E0C"),
    "HOLD":    ("#FFD60A", "#332B08"),
    "IDLE":    ("#98989D", "#26262C"),
    "OFFLINE": ("#5A5A60", "#222226"),
}

def state_of(status, is_alarm, connected):
    if not connected or "OFFLINE" in status: return "OFFLINE"
    if is_alarm:            return "ALARM"
    if "RUN"  in status:    return "RUN"
    if "HOLD" in status:    return "HOLD"
    return "IDLE"

def summary_of(machines):
    """헤더 가동 요약 (점 색, 문구, 문구 색). 원격 페이지도 같은 문구를 사용"""
    connected = [m for m in machines if getattr(m, "is_connected", False)]
    alarm   = sum(1 for m in connected if getattr(m, "data", {}).get("is_alarm"))
    running = sum(1 for m in connected if "RUN" in getattr(m, "data", {}).get("status", ""))

    if alarm:
        return "#FF453A", f"알람 {alarm}대 발생", "#FF453A"
    if not connected:
        return "#5A5A60", "연결된 장비 없음", COL_MUTED
    if running:
        return "#30D158", f"{running}대 가동 중", COL_TEXT
    return "#98989D", f"{len(connected)}대 대기 중", COL_TEXT

# ── 마우스 호버 시 안내 문구를 띄워주는 툴팁 클래스 ──────────
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tw = None
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        x = self.widget.winfo_rootx() + (self.widget.winfo_width() // 2) - 40
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        self.tw.attributes("-topmost", True)

        label = tk.Label(
            self.tw, text=self.text, justify='center',
            background="#2A2A2A", foreground="#FFFFFF",
            relief='solid', borderwidth=1,
            font=("Malgun Gothic", 10)
        )
        label.pack(ipadx=8, ipady=4)

    def hide(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None
# ─────────────────────────────────────────────────────────────

class AppUI(ctk.CTk):
    def __init__(self, machines):
        super().__init__()

        self.init_width = 640

        self.title("DN Solutions Machine Watcher v2.4")
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=COL_BG)

        # [v2.3] 숫자용 폰트: JetBrains Mono 우선, 없으면 Cascadia → Consolas 순으로 대체
        fams = set(tkfont.families(self))
        self.font_num = next((f for f in ["JetBrains Mono", "Cascadia Mono", "Cascadia Code"] if f in fams), "Consolas")
        self.font_ui = "Malgun Gothic"
        # [v2.4] 아이콘 폰트: Win11 Fluent, Win10은 MDL2 (글리프 코드 동일)
        self.font_icon = "Segoe Fluent Icons" if "Segoe Fluent Icons" in fams else "Segoe MDL2 Assets"
        # [v2.4] 연결 버튼 플러그 아이콘 (연결하기 = 초록, 해제 = 회색)
        self.img_connect    = glyph_image(ICON_PLUG, STATE_COLORS["RUN"][0])
        self.img_disconnect = glyph_image(ICON_PLUG, COL_MUTED)
        self.detail_cb = None   # 패널을 처음 펼칠 때 값을 바로 채우는 콜백 (MainController가 연결)

        self.machines = machines
        self.scroll = None
        self.icon_path = None   # MainController가 아이콘 존재 확인 후 설정
        self.notify_enabled = tk.BooleanVar(value=True)
        self.widgets = {}
        self.is_hidden = False
        self.is_compact = False

        self.drag_start_x = 0
        self.drag_start_y = 0
        self._is_dragging = False
        self._title_drag = None   # [v2.4] 헤더 드래그 시 (마우스-창 좌표 오프셋)

        self.setup_ui()
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        # [v2.4] 기본 타이틀바 제거 → 헤더가 타이틀바 역할 (A안)
        self.overrideredirect(True)
        self.bind("<Map>", self._on_map)
        self._center_window()

    def setup_ui(self):
        # 1. 고정 헤더
        self.header = ctk.CTkFrame(self, height=50, corner_radius=0, fg_color=COL_BG)
        self.header.pack(fill="x", side="top")

        self.header_line = ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=COL_BORDER)
        self.header_line.pack(fill="x", side="top")

        # [v2.3] B안 헤더: 제목 대신 실시간 가동 요약
        self.summary_dot = ctk.CTkLabel(
            self.header, text="●", font=("Segoe UI", 13),
            text_color=STATE_COLORS["OFFLINE"][0]
        )
        self.summary_dot.pack(side="left", padx=(20, 7), pady=13)

        self.summary_lbl = ctk.CTkLabel(
            self.header, text="연결된 장비 없음",
            font=(self.font_ui, 14, "bold"), text_color=COL_TEXT
        )
        self.summary_lbl.pack(side="left")

        self.summary_sub = ctk.CTkLabel(
            self.header, text="",
            font=(self.font_ui, 12), text_color=COL_SUB
        )
        self.summary_sub.pack(side="left", padx=(7, 0), pady=(2, 0))

        # [v2.4] 창 조작 버튼 (최대화 없음). 닫기는 기존처럼 트레이로 숨김
        self.close_btn = ctk.CTkButton(
            self.header, text=ICON_CLOSE, width=46, height=50, corner_radius=0,
            fg_color="transparent", hover_color=COL_CLOSE_HOV, text_color=COL_VALUE,
            font=(self.font_icon, 10), command=self.hide_window
        )
        self.close_btn.pack(side="right")
        self.close_btn.bind("<Enter>", lambda e: self.close_btn.configure(text_color="#FFFFFF"))
        self.close_btn.bind("<Leave>", lambda e: self.close_btn.configure(text_color=COL_VALUE))

        self.min_btn = ctk.CTkButton(
            self.header, text=ICON_MINIMIZE, width=46, height=50, corner_radius=0,
            fg_color="transparent", hover_color=COL_BTN, text_color=COL_VALUE,
            font=(self.font_icon, 10), command=self.minimize_window
        )
        self.min_btn.pack(side="right")

        ctk.CTkFrame(self.header, width=1, height=18, corner_radius=0,
                     fg_color=COL_BORDER).pack(side="right", padx=6)

        self.compact_btn = self._header_icon_btn(ICON_COMPACT, self.toggle_compact_mode)
        self.compact_tooltip = ToolTip(self.compact_btn, "최소화 모드")

        self.notify_btn = self._header_icon_btn(ICON_BELL, self.toggle_notify)
        self.notify_tooltip = ToolTip(self.notify_btn, "알림: 켜짐")
        self._style_toggle_btn(self.notify_btn, True)   # 시작 시 알림 켜짐

        # [v2.2 추가] 장비 설정 버튼 (command는 MainController가 연결)
        self.settings_btn = self._header_icon_btn(ICON_SETTINGS)
        self.settings_tooltip = ToolTip(self.settings_btn, "장비 설정")

        # [v2.4] 원격 모니터링 버튼 (command는 MainController가 연결)
        self.remote_btn = self._header_icon_btn(ICON_REMOTE)
        self.remote_tooltip = ToolTip(self.remote_btn, "원격 모니터링: 꺼짐\n우클릭: 설정")

        # 헤더 빈 영역을 잡고 창 이동
        for w_item in (self.header, self.summary_dot, self.summary_lbl, self.summary_sub):
            w_item.bind("<ButtonPress-1>", self._title_press)
            w_item.bind("<B1-Motion>", self._title_motion)

        # 2. 메인 컨테이너 영역 (장비 카드)
        self.build_machine_cards()

    def _header_icon_btn(self, glyph, command=None):
        btn = ctk.CTkButton(
            self.header, text=glyph, width=32, height=30,
            fg_color="transparent", hover_color=COL_BTN, text_color=COL_MUTED,
            font=(self.font_icon, 15), command=command
        )
        btn.pack(side="right", padx=(0, 2), pady=10)
        return btn

    def build_machine_cards(self):
        """장비 목록 기준으로 카드 UI를 (재)생성. 설정 변경 시에도 호출됨."""
        if self.scroll is not None:
            self.scroll.destroy()

        calc_height = 110 + (len(self.machines) * 106)
        self.init_height = max(280, min(850, calc_height))
        self.needs_scroll = calc_height > 850

        if not self.is_compact:
            self.minsize(self.init_width, self.init_height)
            self.geometry(f"{self.init_width}x{self.init_height}")

        if self.needs_scroll:
            self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        else:
            self.scroll = ctk.CTkFrame(self, fg_color="transparent")

        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)
        self.widgets = {}
        self.expanded = set()   # [v2.4] 부하·가동률 패널이 펼쳐진 장비 IP

        for m in self.machines:
            card = ctk.CTkFrame(self.scroll, fg_color=COL_CARD, corner_radius=10)
            card.pack(fill="x", pady=5)

            # --- [A] 전체 모드용 컨테이너 ---
            full_f = ctk.CTkFrame(card, fg_color="transparent")
            full_f.pack(fill="x")

            strip = ctk.CTkFrame(full_f, width=5, height=10, corner_radius=3,
                                 fg_color=STATE_COLORS["OFFLINE"][0])
            strip.pack(side="left", fill="y", padx=(8, 0), pady=8)

            body = ctk.CTkFrame(full_f, fg_color="transparent")
            body.pack(side="left", fill="both", expand=True, padx=(12, 16), pady=10)

            row1 = ctk.CTkFrame(body, fg_color="transparent")
            row1.pack(fill="x")
            name_l = ctk.CTkLabel(row1, text=m.name, font=(self.font_ui, 16, "bold"), text_color=COL_TEXT)
            name_l.pack(side="left")
            ip_l = ctk.CTkLabel(row1, text=m.ip, font=(self.font_num, 11), text_color=COL_SUB)
            ip_l.pack(side="left", padx=(10, 0), pady=(3, 0))
            chev = ctk.CTkLabel(row1, text=ICON_CHEV_DN, width=16, font=(self.font_icon, 10), text_color=COL_SUB)
            chev.pack(side="right", padx=(8, 0))
            badge = ctk.CTkLabel(row1, text="OFFLINE", font=(self.font_ui, 11, "bold"),
                                 text_color=STATE_COLORS["OFFLINE"][0],
                                 fg_color=STATE_COLORS["OFFLINE"][1],
                                 corner_radius=11, width=86, height=24)
            badge.pack(side="right")

            row2 = ctk.CTkFrame(body, fg_color="transparent")
            row2.pack(fill="x", pady=(10, 0))
            # [v2.4] 연결 버튼 A안: 초록 테두리 + 플러그 아이콘 (연결 후엔 회색 '해제')
            btn = ctk.CTkButton(row2, text="연결", image=self.img_connect, compound="left",
                                width=66, height=26, corner_radius=6, border_width=1,
                                fg_color="transparent", hover_color=COL_ON_BG,
                                border_color=STATE_COLORS["RUN"][0], text_color=STATE_COLORS["RUN"][0],
                                font=(self.font_ui, 11, "bold"))
            btn.pack(side="left")

            metric_vals = {}
            for lbl, key in (("MODE", "mode"), ("TOOL", "tool"), ("PRG", "program")):
                ctk.CTkLabel(row2, text=lbl, font=(self.font_ui, 10), text_color=COL_SUB).pack(side="left", padx=(20, 5))
                v = ctk.CTkLabel(row2, text="-", font=(self.font_num, 14), text_color=COL_SUB)
                v.pack(side="left")
                metric_vals[key] = v

            time_l = ctk.CTkLabel(row2, text="-", font=(self.font_num, 22, "bold"), text_color=COL_SUB)
            time_l.pack(side="right")

            # [v2.4] 알람 목록 (C안) — 알람일 때만 _render_alarms가 채워서 pack
            alm_f = ctk.CTkFrame(body, fg_color="transparent", height=10)

            # [v2.4] 부하·가동률 패널 (A안) — 카드를 누르면 펼침, 내용은 첫 데이터에서 축 구성 보고 생성
            # 높이를 애니메이션하기 위해 크기 고정(propagate 끔)된 tk.Frame으로 내용(inner)을 잘라 보여준다
            det_f = tk.Frame(body, bg=COL_CARD, height=1, bd=0, highlightthickness=0)
            det_f.pack_propagate(False)

            # --- [B] 최소화 모드용 컨테이너 ---
            comp_f = ctk.CTkFrame(card, fg_color="transparent", height=40)

            # [v2.3] 배지 없이 색깔 바만으로 상태 구분 (창 크기 최소화 목적)
            c_strip = ctk.CTkFrame(comp_f, width=5, height=10, corner_radius=3,
                                   fg_color=STATE_COLORS["OFFLINE"][0])
            c_strip.pack(side="left", fill="y", padx=(6, 0), pady=5)

            c_name = ctk.CTkLabel(comp_f, text=m.name, font=(self.font_ui, 14, "bold"), text_color=COL_TEXT)
            c_name.pack(side="left", padx=(8, 6), pady=7)

            c_time = ctk.CTkLabel(comp_f, text="-", font=(self.font_num, 14, "bold"), text_color=COL_SUB)
            c_time.pack(side="right", padx=(0, 10))

            self.widgets[m.ip] = {
                "card": card, "full_f": full_f, "comp_f": comp_f, "btn": btn,
                "strip": strip, "badge": badge,
                "mode": metric_vals["mode"], "tool": metric_vals["tool"], "program": metric_vals["program"], "time": time_l,
                "c_strip": c_strip, "c_time": c_time,
                "alm_f": alm_f, "alm_key": (), "row2": row2,
                "chev": chev, "det_f": det_f, "det": None,
            }

            for w_item in [card, comp_f, c_name, c_time, c_strip]:
                w_item.bind("<ButtonPress-1>", self.on_drag_start)
                w_item.bind("<B1-Motion>", self.on_drag_motion)
                w_item.bind("<ButtonRelease-1>", self.on_drag_release)
            self._bind_toggle(full_f, m.ip, skip=btn)

    # ── [v2.4] 카드 클릭 → 부하·가동률 패널 펼치기/접기 ──────
    def _bind_toggle(self, widget, ip, skip=None):
        """widget 아래 모든 tk 위젯에 클릭 바인딩 (연결 버튼은 제외).
        tk는 이벤트가 부모로 전달되지 않으므로 클릭된 위젯 하나에서만 한 번 실행된다."""
        path = str(widget)
        if skip is not None and (path == str(skip) or path.startswith(str(skip) + ".")):
            return
        tk.Misc.bind(widget, "<Button-1>", lambda e: self.toggle_detail(ip), add="+")
        for child in widget.winfo_children():
            self._bind_toggle(child, ip, skip)

    def toggle_detail(self, ip):
        w = self.widgets.get(ip)
        if not w or self.is_compact:
            return
        opening = ip not in self.expanded
        if opening:
            self.expanded.add(ip)
            if w["det"] is None:
                # 보통은 prepare_detail이 미리 만들어 두지만, 아직 없으면 지금 만든다 (축 구성은 장비 데이터에서)
                m = next((m for m in self.machines if m.ip == ip), None)
                axes = (getattr(m, "data", None) or {}).get("axis_loads") or []
                self._build_detail(ip, tuple(n for n, _ in axes))
                self.update_idletasks()   # 방금 만든 패널의 높이를 알아야 하므로 (드문 경우라 한 번만)
        else:
            self.expanded.discard(ip)
        w["chev"].configure(text=ICON_CHEV_UP if opening else ICON_CHEV_DN)
        self._animate_detail(ip, opening)

    def _animate_detail(self, ip, opening):
        """[v2.4] 0.2초 동안 패널 높이(와 창 높이)를 ease-out으로 늘리거나 줄인다.
        도중에 다시 누르면 지금 높이에서 반대 방향으로 이어서 움직인다."""
        w = self.widgets[ip]
        f = w["det_f"]
        if w.get("anim"):
            self.after_cancel(w["anim"])
        w["anim_since"] = time.monotonic()
        # 클릭 순간 레이아웃 재계산(update_idletasks, 수십 ms)을 하지 않도록 이미 계산된 크기만 읽는다
        start = f.winfo_height() if f.winfo_ismapped() else 1
        inner = w["det"]["inner"]
        target = inner.winfo_reqheight() if opening else 1
        # 패널 위젯 30여 개를 매 프레임 다시 그리면 프레임당 40ms 넘게 걸려 끊긴다 →
        # 움직이는 동안은 패널을 찍어 둔 이미지 한 장으로 대신 보여주고, 끝나면 실제 위젯으로 돌린다
        if not opening and inner.winfo_ismapped():
            w["snap"] = self._panel_snapshot(ip) or w.get("snap")
        self._show_snapshot(ip, True)
        if opening:
            # 창 크기를 매 프레임 바꾸면 전체 레이아웃을 다시 계산해 뚝뚝 끊긴다 →
            # 펼칠 때는 창을 먼저 최종 높이로 늘려 두고, 접을 때는 끝난 뒤에 줄인다 (빈 공간은 배경색이라 티가 안 남)
            if not self.needs_scroll:
                need = self.header.winfo_reqheight() + 1 + self.scroll.winfo_reqheight() + 20 + (target - start)
                h = max(self.init_height, min(850, need))
                if h > self.winfo_height():
                    self.geometry(f"{self.init_width}x{h}")
            if not f.winfo_ismapped():
                f.configure(height=1)
                f.pack(fill="x")
        clock = {}

        def begin():
            # 창 늘리기·패널 배치가 화면에 반영된 뒤부터 시간을 잰다 — 첫 프레임이 무거워도 중간을 건너뛰지 않게
            clock["t0"] = time.monotonic()
            step()

        def step():
            t = min(1.0, (time.monotonic() - clock["t0"]) * 1000 / ANIM_MS)
            ease = 1 - (1 - t) ** 3
            f.configure(height=max(1, round(start + (target - start) * ease)))
            self.after_idle(self._repaint_background)
            # 마지막 높이를 먼저 화면에 그린 뒤, 무거운 마무리(실제 패널로 교체·창 높이 조정)는 다음 프레임에
            w["anim"] = self.after(ANIM_STEP_MS, step if t < 1 else finish)

        def finish():
            if opening:
                # 최신 값을 채운 실제 패널을 스냅샷 '아래'에 먼저 그려 두고, 다 그려진 뒤 스냅샷을 걷어낸다
                # (바로 바꾸면 위젯이 그려지는 동안 패널이 잠깐 비어 보임)
                if self.detail_cb:
                    self.detail_cb(ip)
                self._show_snapshot(ip, False, keep_snapshot=True)
                w["anim"] = self.after(SWAP_DELAY_MS, reveal)
            else:
                w["anim"] = None
                f.pack_forget()
                self.fit_height()

        def reveal():
            w["anim"] = None
            if w.get("snap_lbl"):
                w["snap_lbl"].place_forget()
            self.fit_height()
        w["anim"] = self.after_idle(begin)

    def _repaint_background(self):
        """카드가 움직이며 드러난 배경을 바로 다시 그리게 한다 — Tk가 이 영역을 무효화하지 않아
        접을 때 아래 카드의 예전 모습이 줄줄이 잔상으로 남던 문제 (레이아웃이 끝난 뒤 after_idle로 호출)"""
        canvas = getattr(self.scroll, "_canvas", None)   # CTkFrame 배경 캔버스
        if canvas is not None:
            _user32.RedrawWindow(canvas.winfo_id(), None, None, RDW_INVALIDATE | RDW_ERASE)

    @property
    def animating(self):
        """펼침/접힘 애니메이션 중인지 — 그동안 MainController는 장비 폴링을 잠시 미룬다 (화면 끊김 방지)"""
        # 혹시 애니메이션 도중 예외로 anim이 안 지워져도 폴링이 영영 멈추지 않게 2초 넘은 건 무시
        now = time.monotonic()
        return any(w.get("anim") and now - w.get("anim_since", 0) < 2 for w in self.widgets.values())

    def _panel_snapshot(self, ip):
        """펼쳐진 패널 모습을 이미지로 (다음 펼침/접힘 애니메이션에 사용, 0.2초라 값이 조금 지나도 티 안 남)"""
        inner = self.widgets[ip]["det"]["inner"]
        try:
            return ImageTk.PhotoImage(capture_screen(inner.winfo_rootx(), inner.winfo_rooty(),
                                                     inner.winfo_width(), inner.winfo_height()))
        except Exception:
            return None

    def _show_snapshot(self, ip, on, keep_snapshot=False):
        """on: 실제 패널 대신 스냅샷(없으면 빈 칸)을 보여줌 / off: 실제 패널로 복귀
        keep_snapshot: 실제 패널을 놓되 스냅샷은 위에 그대로 덮어 둠 (나중에 걷어냄)"""
        w = self.widgets[ip]
        inner = w["det"]["inner"]
        lbl = w.get("snap_lbl")
        if on:
            inner.place_forget()
            if w.get("snap"):
                if not lbl:
                    lbl = w["snap_lbl"] = tk.Label(w["det_f"], bd=0, highlightthickness=0, bg=COL_CARD)
                    self._bind_toggle(lbl, ip)
                lbl.configure(image=w["snap"])
                lbl.place(x=0, y=0)
                lbl.lift()
        else:
            inner.place(x=0, y=0, relwidth=1)
            if lbl:
                if keep_snapshot and lbl.winfo_ismapped():
                    lbl.lift()   # 나중에 만든 inner가 위로 올라오지 않게
                else:
                    lbl.place_forget()

    def _snap_detail_height(self, ip):
        """펼친 상태에서 내용이 바뀌었을 때(축 구성 변경 등) 패널 높이를 바로 맞춤"""
        w = self.widgets[ip]
        if ip in self.expanded and not w.get("anim"):
            self.update_idletasks()
            w["det_f"].configure(height=w["det"]["inner"].winfo_reqheight())
            self.fit_height()

    def _build_detail(self, ip, axis_names):
        """축 구성(이름·개수)에 맞춰 패널 내용을 만든다. 축 구성이 바뀌면 다시 만든다."""
        w = self.widgets[ip]
        if w["det"]:
            w["det"]["inner"].destroy()
        w["snap"] = None   # 축 구성이 바뀌면 예전 스냅샷은 크기가 맞지 않음
        f = ctk.CTkFrame(w["det_f"], fg_color="transparent")   # 축 구성이 바뀌면 통째로 교체
        # pack이면 바깥 높이가 줄 때 내용을 찌그러뜨리며 매 프레임 재배치(느림) → place로 원래 크기 고정, 바깥이 잘라서 보여줌
        f.place(x=0, y=0, relwidth=1)
        d = {"axis_names": axis_names, "axes": {}, "inner": f}

        ctk.CTkFrame(f, height=1, corner_radius=0, fg_color=COL_BORDER).pack(fill="x", pady=(10, 9))

        sp = ctk.CTkFrame(f, fg_color="transparent")
        sp.pack(fill="x")
        ctk.CTkLabel(sp, text="스핀들", width=46, anchor="w", height=18,
                     font=(self.font_ui, 10), text_color=COL_SUB).pack(side="left")
        d["sp_rpm"] = ctk.CTkLabel(sp, text="-", width=76, anchor="e", height=18,
                                   font=(self.font_num, 10), text_color=COL_SUB)
        d["sp_rpm"].pack(side="right")
        d["sp_pct"] = ctk.CTkLabel(sp, text="-", width=42, anchor="e", height=18,
                                   font=(self.font_num, 11, "bold"), text_color=COL_SUB)
        d["sp_pct"].pack(side="right")
        d["sp_bar"] = ctk.CTkProgressBar(sp, height=9, corner_radius=4, fg_color=COL_BTN,
                                         progress_color=COL_BTN, border_width=0)
        d["sp_bar"].set(0)
        d["sp_bar"].pack(side="left", fill="x", expand=True, padx=(4, 0))

        if axis_names:
            grid = ctk.CTkFrame(f, fg_color="transparent")
            grid.pack(fill="x", pady=(9, 0))
            for i, name in enumerate(axis_names):
                grid.grid_columnconfigure(i, weight=1, uniform="axis")
                cell = ctk.CTkFrame(grid, fg_color="transparent")
                cell.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
                top = ctk.CTkFrame(cell, fg_color="transparent")
                top.pack(fill="x")
                ctk.CTkLabel(top, text=name, height=16, font=(self.font_num, 10), text_color=COL_SUB).pack(side="left")
                pct = ctk.CTkLabel(top, text="-", height=16, font=(self.font_num, 10), text_color=COL_SUB)
                pct.pack(side="right")
                bar = ctk.CTkProgressBar(cell, height=6, corner_radius=3, fg_color=COL_BTN,
                                         progress_color=COL_BTN, border_width=0)
                bar.set(0)
                bar.pack(fill="x", pady=(2, 0))
                d["axes"][name] = (bar, pct)

        ut = ctk.CTkFrame(f, fg_color="transparent")
        ut.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(ut, text="오늘 가동률", height=18, font=(self.font_ui, 10), text_color=COL_SUB).pack(side="left")
        d["ut_pct"] = ctk.CTkLabel(ut, text="-", height=18, font=(self.font_num, 12, "bold"), text_color=COL_TEXT)
        d["ut_pct"].pack(side="left", padx=(6, 0))
        d["ut_sub"] = ctk.CTkLabel(ut, text="", height=18, font=(self.font_ui, 10), text_color=COL_SUB)
        d["ut_sub"].pack(side="left", padx=(6, 0))

        # 0시 → 지금 타임라인 (가공 초록 · 알람 빨강)
        d["tl"] = tk.Canvas(f, height=8, bg=COL_BTN, highlightthickness=0, bd=0)
        d["tl"].pack(fill="x", pady=(5, 0))
        d["tl"].bind("<Configure>", lambda e, ip=ip: self._draw_timeline(ip))
        ends = ctk.CTkFrame(f, fg_color="transparent")
        ends.pack(fill="x")
        ctk.CTkLabel(ends, text="0시", height=14, font=(self.font_num, 9), text_color=COL_SUB).pack(side="left")
        d["tl_now"] = ctk.CTkLabel(ends, text="지금", height=14, font=(self.font_num, 9), text_color=COL_SUB)
        d["tl_now"].pack(side="right")
        d["util"] = None

        w["det"] = d
        self._bind_toggle(f, ip)   # 패널을 눌러도 접힘

    def prepare_detail(self, ip, axes):
        """[v2.4] 접혀 있는 동안 패널을 미리 만들어 둔다 — 클릭 순간 위젯 30여 개를 만드느라 0.3초 멈추는 것 방지.
        축 구성이 바뀌었을 때(처음 연결 등)만 다시 만든다."""
        w = self.widgets.get(ip)
        names = tuple(n for n, _ in axes)
        if w and ip not in self.expanded and (w["det"] is None or (names and names != w["det"]["axis_names"])):
            self._build_detail(ip, names)

    def apply_detail(self, ip, data, util, connected):
        """[v2.4] 펼쳐진 카드의 부하·가동률 갱신 (MainController가 펼쳐진 장비만 호출)"""
        w = self.widgets.get(ip)
        if not w or ip not in self.expanded:
            return
        axes = data.get("axis_loads") or []
        names = tuple(n for n, _ in axes)
        if w["det"] is None or (names and names != w["det"]["axis_names"]):
            self._build_detail(ip, names)
            self._snap_detail_height(ip)
        d = w["det"]

        # 값이 0이면 막대 색을 트랙 색과 같게 — 0%일 때 왼쪽 끝에 점이 남는 것 방지
        sp = data.get("spindle_load") if connected else None
        d["sp_bar"].set(min(sp or 0, LOAD_SCALE) / LOAD_SCALE)
        d["sp_bar"].configure(progress_color=load_color(sp) if sp else COL_BTN)
        d["sp_pct"].configure(text=f"{sp}%" if sp is not None else "-", text_color=load_color(sp))
        rpm = data.get("spindle_rpm") if connected else None
        d["sp_rpm"].configure(text=f"{rpm:,}rpm" if rpm is not None else "-")
        loads = dict(axes) if connected else {}
        for name, (bar, pct) in d["axes"].items():
            v = loads.get(name)
            bar.set(min(v or 0, LOAD_SCALE) / LOAD_SCALE)
            bar.configure(progress_color=load_color(v) if v else COL_BTN)
            pct.configure(text=f"{v}%" if v is not None else "-", text_color=COL_VALUE if v is not None else COL_SUB)

        d["util"] = util
        d["ut_pct"].configure(text=f"{round(util['ratio'] * 100)}%")
        h, m = divmod(util["run_sec"] // 60, 60)
        d["ut_sub"].configure(text=f"· 가공 {h}시간 {m}분" if h else f"· 가공 {m}분")
        d["tl_now"].configure(text="지금 " + datetime.datetime.now().strftime("%H:%M"))
        self._draw_timeline(ip)

    def _draw_timeline(self, ip):
        d = (self.widgets.get(ip) or {}).get("det")
        if not d or not d["util"]:
            return
        c, util = d["tl"], d["util"]
        c.delete("all")
        width, total = c.winfo_width(), util["now_sec"]
        for start, end, st in util["segments"]:
            x0, x1 = width * start / total, max(width * end / total, width * start / total + 1)
            c.create_rectangle(x0, 0, x1, 8, width=0, fill=STATE_COLORS[st][0])

    # ── [v2.3] 상태를 UI에 일괄 반영 ──────────────────────────
    def apply_status(self, ip, mode, status, tool, cyc, is_alarm, connected, alarms=(), program=None):
        w = self.widgets.get(ip)
        if not w: return

        state = state_of(status, is_alarm, connected)
        accent, badge_bg = STATE_COLORS[state]

        # [v2.4] 알람 목록은 내용이 바뀔 때만 다시 그림 (0.5초마다 위젯 재생성 방지)
        alarms = alarms if state == "ALARM" else ()
        key = tuple((a["code"], a["msg"]) for a in alarms)
        if key != w["alm_key"]:
            w["alm_key"] = key
            self._render_alarms(w, alarms)
            self.fit_height()

        if state == "ALARM":     badge_txt = "▲ ALARM" + (f" {len(alarms)}" if len(alarms) > 1 else "")
        elif state == "RUN":     badge_txt = "● RUN"
        elif state == "HOLD":    badge_txt = "HOLD"
        elif state == "OFFLINE": badge_txt = "OFFLINE"
        else:                    badge_txt = status

        for s in (w["strip"], w["c_strip"]):
            s.configure(fg_color=accent)
        w["badge"].configure(text=badge_txt, text_color=accent, fg_color=badge_bg)

        val_col = COL_VALUE if connected else COL_SUB
        w["mode"].configure(text=mode if connected else "-", text_color=val_col)
        w["tool"].configure(text=tool if connected else "-", text_color=val_col)
        # [v2.4] 프로그램명 — 길면 사이클 타임을 밀어내지 않게 줄임
        prg = (program if len(program) <= 14 else program[:13] + "…") if connected and program else "-"
        w["program"].configure(text=prg, text_color=val_col)

        t_col = accent if state == "ALARM" else (COL_TEXT if connected else COL_SUB)
        t_txt = cyc if connected else "-"
        w["time"].configure(text=t_txt, text_color=t_col)
        w["c_time"].configure(text=t_txt, text_color=t_col)

        # 이미지가 있는 버튼은 configure마다 다시 그리므로 연결 상태가 바뀔 때만 갱신
        if w.get("btn_on") != connected:
            w["btn_on"] = connected
            if connected:
                w["btn"].configure(text="해제", image=self.img_disconnect, border_color=COL_OUTLINE,
                                   text_color=COL_MUTED, hover_color=COL_BTN)
            else:
                w["btn"].configure(text="연결", image=self.img_connect, border_color=STATE_COLORS["RUN"][0],
                                   text_color=STATE_COLORS["RUN"][0], hover_color=COL_ON_BG)

    def _render_alarms(self, w, alarms):
        # CTkFrame의 내부 캔버스까지 지우지 않도록, 내용은 매번 새 안쪽 프레임에 그린다
        if w.get("alm_inner"):
            w["alm_inner"].destroy()
            w["alm_inner"] = None
        if not alarms:
            w["alm_f"].pack_forget()
            return

        frame = w["alm_inner"] = ctk.CTkFrame(w["alm_f"], fg_color="transparent")
        frame.pack(fill="x")
        ctk.CTkFrame(frame, height=1, corner_radius=0, fg_color=COL_ALM_LINE).grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        for i, a in enumerate(alarms, start=1):
            ctk.CTkLabel(frame, text=a["code"], height=20, font=(self.font_num, 12, "bold"),
                         text_color=COL_ALM_CODE).grid(row=i, column=0, sticky="nw", padx=(0, 12))
            # 긴 메시지는 창을 넓히지 않고 줄바꿈
            ctk.CTkLabel(frame, text=a["msg"], height=20, font=(self.font_ui, 12), text_color=COL_ALM_MSG,
                         anchor="w", justify="left", wraplength=400).grid(row=i, column=1, sticky="w")
            ctk.CTkLabel(frame, text=a["since"], height=20, font=(self.font_num, 11),
                         text_color=COL_ALM_SUB).grid(row=i, column=2, sticky="ne", padx=(12, 0))
        frame.grid_columnconfigure(1, weight=1)
        w["alm_f"].pack(fill="x", pady=(10, 0), after=w["row2"])   # 펼침 패널보다 위(정보 줄 바로 아래)

    def fit_height(self):
        """[v2.4] 알람 목록이 펼쳐지거나 접히면 창 높이를 내용에 맞춤 (전체 모드, 스크롤 없는 경우만)"""
        if self.is_compact or self.needs_scroll:
            return
        self.update_idletasks()
        need = self.header.winfo_reqheight() + 1 + self.scroll.winfo_reqheight() + 20
        h = max(self.init_height, min(850, need))
        if h != self.winfo_height():
            self.geometry(f"{self.init_width}x{h}")

    # ── [v2.3] 헤더 실시간 가동 요약 갱신 ─────────────────────
    def update_summary(self):
        col, txt, txt_col = summary_of(self.machines)
        self.summary_dot.configure(text_color=col)
        self.summary_lbl.configure(text=txt, text_color=txt_col)
        self.summary_sub.configure(text=f"/  전체 {len(self.machines)}대")

    # ── 알림 토글 로직 ──────────────────────────────────────
    def toggle_notify(self):
        current_state = not self.notify_enabled.get()
        self.notify_enabled.set(current_state)

        self.notify_btn.configure(text=ICON_BELL if current_state else ICON_BELL_OFF)
        self.notify_tooltip.text = "알림: 켜짐" if current_state else "알림: 꺼짐"
        self._style_toggle_btn(self.notify_btn, current_state)

    def _style_toggle_btn(self, btn, on):
        """[v2.4] 켜진 토글 버튼(📡·🔔)은 초록 배경으로 강조해 꺼진 상태와 구분"""
        if on:
            btn.configure(fg_color=COL_ON_BG, hover_color=COL_ON_BG, text_color=STATE_COLORS["RUN"][0])
        else:
            btn.configure(fg_color="transparent", hover_color=COL_BTN, text_color=COL_MUTED)

    # ── [v2.4] 원격 모니터링 버튼 상태 표시 ──────────────────
    def set_remote_state(self, on, urls=()):
        self._style_toggle_btn(self.remote_btn, on)
        if on:
            self.remote_tooltip.text = "원격 모니터링: 켜짐 (절전 차단 중)\n" + "\n".join(urls) + "\n우클릭: 설정"
        else:
            self.remote_tooltip.text = "원격 모니터링: 꺼짐\n우클릭: 설정"
    # ─────────────────────────────────────────────────────────────

    def on_drag_start(self, event):
        if self.is_compact:
            self.drag_start_x = event.x_root
            self.drag_start_y = event.y_root
            self._is_dragging = False

    def on_drag_motion(self, event):
        if self.is_compact:
            dx = event.x_root - self.drag_start_x
            dy = event.y_root - self.drag_start_y
            if abs(dx) > 3 or abs(dy) > 3:
                self._is_dragging = True
                new_x = self.winfo_x() + dx
                new_y = self.winfo_y() + dy
                self.geometry(f"+{new_x}+{new_y}")
                self.drag_start_x = event.x_root
                self.drag_start_y = event.y_root

    def on_drag_release(self, event):
        if self.is_compact:
            if not self._is_dragging:
                self.restore_from_click()
            self._is_dragging = False

    def toggle_compact_mode(self):
        if not self.is_compact:
            self.is_compact = True

            self.attributes("-topmost", True)

            self.header.pack_forget()
            self.header_line.pack_forget()
            for ip, w_ref in self.widgets.items():
                w_ref["full_f"].pack_forget()
                w_ref["comp_f"].pack(fill="x")

            # [v2.3] 고정 계산식 대신 실제 콘텐츠 높이를 측정해 기계 대수에 맞춤
            self.update_idletasks()
            h = min(self.scroll.winfo_reqheight() + 20, 850)
            w = 240

            self.minsize(w, h)
            self.geometry(f"{w}x{h}")
        else:
            self.is_compact = False

            self.minsize(self.init_width, self.init_height)
            self.geometry(f"{self.init_width}x{self.init_height}")
            self.attributes("-topmost", False)

            self.scroll.pack_forget()
            self.header.pack(fill="x", side="top")
            self.header_line.pack(fill="x", side="top")
            self.scroll.pack(fill="both", expand=True, padx=10, pady=10)

            for ip, w_ref in self.widgets.items():
                w_ref["comp_f"].pack_forget()
                w_ref["full_f"].pack(fill="x")
            self.fit_height()   # 최소화 모드 중에 생긴 알람 목록 반영

    def restore_from_click(self):
        if self.is_compact:
            self.toggle_compact_mode()

    def hide_window(self):
        self.withdraw()
        self.is_hidden = True

    def show_window(self):
        self.deiconify()
        self.is_hidden = False

    # ── [v2.4] 테두리 없는 창 (커스텀 타이틀바) ───────────────
    def _title_press(self, event):
        self._title_drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _title_motion(self, event):
        if self._title_drag:
            dx, dy = self._title_drag
            self.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _hwnd(self):
        return _user32.GetParent(self.winfo_id())

    def _on_map(self, event):
        if event.widget is self:
            self._apply_frameless_style()

    def _apply_frameless_style(self):
        """overrideredirect 창은 작업표시줄에서 빠지고 최소화가 안 되므로
        확장 스타일을 일반 앱 창(APPWINDOW)으로 바꿔준다. 첫 표시 때 한 번만 실제 변경됨."""
        hwnd = self._hwnd()
        ex = _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        want = (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        if want == ex:
            return
        _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, want)
        _user32.SetWindowLongPtrW(hwnd, GWL_STYLE, _user32.GetWindowLongPtrW(hwnd, GWL_STYLE) | WS_MINIMIZEBOX)
        # Win11 둥근 모서리 + 테두리색 (Win10에서는 무시됨)
        try:
            r, g, b = (int(COL_BORDER[i:i + 2], 16) for i in (1, 3, 5))
            dwm = ctypes.windll.dwmapi
            dwm.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                      ctypes.byref(ctypes.c_int(DWMWCP_ROUND)), 4)
            dwm.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR,
                                      ctypes.byref(ctypes.c_uint(r | g << 8 | b << 16)), 4)
        except Exception:
            pass
        # 스타일 변경을 작업표시줄에 반영하려면 다시 표시해야 함
        self.withdraw()
        self.after(10, self.deiconify)

    def _center_window(self):
        x = (self.winfo_screenwidth() - self.init_width) // 2
        y = (self.winfo_screenheight() - self.init_height) // 3
        self.geometry(f"{self.init_width}x{self.init_height}+{x}+{y}")

    def minimize_window(self):
        # overrideredirect 창은 tk의 iconify()가 막혀 있어 Win32로 직접 최소화
        _user32.ShowWindow(self._hwnd(), SW_MINIMIZE)

    def show_emergency_popup(self, machine_name, alarms=()):
        popup = ctk.CTkToplevel(self, fg_color=COL_BG)
        popup.title("ALARM")
        # [v2.4] 알람 내용 길이에 따라 높이가 달라지므로 고정 크기 대신 내용 크기로 (너비만 300 확보)
        tk.Frame(popup, width=300, height=1, bg=COL_BG).pack()
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        # customtkinter가 생성 직후(200ms) 기본 아이콘으로 덮어쓰므로 그 뒤에 적용
        if self.icon_path:
            popup.after(250, lambda: popup.iconbitmap(self.icon_path))

        circle = ctk.CTkFrame(popup, width=56, height=56, corner_radius=28, fg_color="#33100D")
        circle.pack(pady=(24, 10))
        circle.pack_propagate(False)
        ctk.CTkLabel(circle, text="⚠", font=("Segoe UI Emoji", 24), text_color="#FF453A").pack(expand=True)

        ctk.CTkLabel(popup, text="ALARM", font=(self.font_ui, 18, "bold"), text_color="#FF453A").pack()
        ctk.CTkLabel(popup, text=machine_name, font=(self.font_ui, 15, "bold"), text_color=COL_TEXT).pack(pady=(2, 0))

        # [v2.4] 알람 번호·내용 (최대 3건, 나머지는 건수만)
        if alarms:
            box = ctk.CTkFrame(popup, fg_color=COL_CARD, corner_radius=8)
            box.pack(fill="x", padx=20, pady=(12, 4))
            for a in alarms[:3]:
                ctk.CTkLabel(box, text=a["code"], height=18, anchor="w", font=(self.font_num, 12, "bold"),
                             text_color=COL_ALM_CODE).pack(fill="x", padx=12, pady=(8, 0))
                ctk.CTkLabel(box, text=a["msg"], height=18, anchor="w", justify="left", wraplength=236,
                             font=(self.font_ui, 12), text_color=COL_VALUE).pack(fill="x", padx=12)
            if len(alarms) > 3:
                ctk.CTkLabel(box, text=f"외 {len(alarms) - 3}건", height=18, anchor="w",
                             font=(self.font_ui, 11), text_color=COL_MUTED).pack(fill="x", padx=12, pady=(4, 0))
            ctk.CTkFrame(box, height=8, fg_color="transparent").pack()

        now = alarms[0]["since"] if alarms else datetime.datetime.now().strftime("%H:%M:%S")
        ctk.CTkLabel(popup, text=f"{now} 발생 · 장비 상태를 확인하세요",
                     font=(self.font_ui, 11), text_color=COL_MUTED).pack(pady=(0, 14))
        ctk.CTkButton(popup, text="확인", width=120, height=30, corner_radius=8,
                      fg_color="#33100D", hover_color="#4A1815", text_color="#FF6961",
                      border_width=1, border_color="#6E2420",
                      font=(self.font_ui, 12, "bold"), command=popup.destroy).pack(pady=(0, 20))
        self.bell()


# ── [v2.2 추가] 장비 추가/삭제 설정 창 ──────────────────────────
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, machines_data, on_save):
        super().__init__(master, fg_color=COL_BG)
        self.title("장비 설정")
        self.geometry("520x420")
        self.attributes("-topmost", True)
        self.grab_set()  # 설정 중에는 메인 창 조작 잠금

        # customtkinter가 생성 직후(200ms) 기본 아이콘으로 덮어쓰므로 그 뒤에 적용
        icon = getattr(master, "icon_path", None)
        if icon:
            self.after(250, lambda: self.iconbitmap(icon))
        self.on_save = on_save
        self.rows = []

        self.font_ui  = getattr(master, "font_ui", "Malgun Gothic")
        self.font_num = getattr(master, "font_num", "Consolas")

        # 컬럼 헤더
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=15, pady=(15, 0))
        for text, w in [("장비명", 140), ("IP 주소", 160), ("포트", 80)]:
            ctk.CTkLabel(head, text=text, width=w, anchor="w",
                         text_color=COL_SUB, font=(self.font_ui, 11)).pack(side="left", padx=5)

        # 장비 목록 영역
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        for m in machines_data:
            self.add_row(m["name"], m["ip"], str(m.get("port", 8193)))

        # 하단 버튼
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=15, pady=(0, 15))
        ctk.CTkButton(bottom, text="＋ 장비 추가", width=110,
                      fg_color="transparent", hover_color=COL_CARD,
                      border_width=1, border_color="#3A3A42",
                      text_color=COL_MUTED, font=(self.font_ui, 12),
                      command=lambda: self.add_row()).pack(side="left")
        ctk.CTkButton(bottom, text="저장", width=90,
                      fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOV,
                      text_color="#FFFFFF", font=(self.font_ui, 12, "bold"),
                      command=self.save).pack(side="right")
        ctk.CTkButton(bottom, text="취소", width=90,
                      fg_color=COL_BTN, hover_color=COL_BTN_HOV,
                      text_color=COL_MUTED, font=(self.font_ui, 12),
                      command=self.destroy).pack(side="right", padx=(0, 8))

    def _entry(self, row, width, font, placeholder=""):
        return ctk.CTkEntry(row, width=width, font=font, placeholder_text=placeholder,
                            fg_color=COL_CARD, border_color=COL_BORDER, border_width=1,
                            text_color=COL_VALUE)

    def add_row(self, name="", ip="", port="8193"):
        row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        row.pack(fill="x", pady=3)

        e_name = self._entry(row, 140, (self.font_ui, 12), "예: DVF5000")
        e_name.pack(side="left", padx=5)
        e_ip = self._entry(row, 160, (self.font_num, 12), "예: 192.168.10.109")
        e_ip.pack(side="left", padx=5)
        e_port = self._entry(row, 80, (self.font_num, 12))
        e_port.pack(side="left", padx=5)

        if name: e_name.insert(0, name)
        if ip:   e_ip.insert(0, ip)
        e_port.insert(0, port)

        del_btn = ctk.CTkButton(row, text="✕", width=32, height=28,
                                fg_color="#2A1513", hover_color="#3A1B18",
                                text_color="#FF6961",
                                command=lambda: self.delete_row(row))
        del_btn.pack(side="left", padx=5)

        self.rows.append((row, e_name, e_ip, e_port))

    def delete_row(self, row_frame):
        self.rows = [r for r in self.rows if r[0] is not row_frame]
        row_frame.destroy()

    def save(self):
        data = []
        seen_ips = set()
        for _, e_name, e_ip, e_port in self.rows:
            name = e_name.get().strip()
            ip   = e_ip.get().strip()
            port = e_port.get().strip()

            if not name or not ip:
                messagebox.showwarning("입력 오류", "장비명과 IP 주소를 모두 입력해 주세요.", parent=self)
                return
            try:
                port_num = int(port)
                if not (1 <= port_num <= 65535): raise ValueError
            except ValueError:
                messagebox.showwarning("입력 오류", f"[{name}] 포트는 1~65535 사이의 숫자여야 합니다.", parent=self)
                return
            if ip in seen_ips:
                messagebox.showwarning("입력 오류", f"IP 주소가 중복되었습니다: {ip}", parent=self)
                return
            seen_ips.add(ip)
            data.append({"name": name, "ip": ip, "port": port_num})

        if not data:
            messagebox.showwarning("입력 오류", "최소 1대 이상의 장비가 필요합니다.", parent=self)
            return

        self.on_save(data)
        self.destroy()


# ── [v2.4] 원격 모니터링 설정 창 (PIN 설정/변경, 외부 주소, 모든 기기 로그아웃) ──
class RemoteDialog(ctk.CTkToplevel):
    def __init__(self, master, has_pin, running, on_save, on_logout_all):
        super().__init__(master, fg_color=COL_BG)
        self.title("원격 모니터링 설정")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.grab_set()

        # customtkinter가 생성 직후(200ms) 기본 아이콘으로 덮어쓰므로 그 뒤에 적용
        icon = getattr(master, "icon_path", None)
        if icon:
            self.after(250, lambda: self.iconbitmap(icon))
        self.has_pin, self.on_save, self.on_logout_all = has_pin, on_save, on_logout_all
        self.font_ui  = getattr(master, "font_ui", "Malgun Gothic")
        self.font_num = getattr(master, "font_num", "Consolas")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", padx=18, pady=(10, 16))
        tk.Frame(body, width=300, height=1, bg=COL_BG).pack()   # 너비 확보 (높이는 내용에 맞춤)

        self._label(body, "외부 접속 주소 (Tailscale Funnel)")
        self.url_lbl = ctk.CTkLabel(body, text="  확인 중…", anchor="w", height=30, corner_radius=6,
                                    fg_color=COL_CARD, text_color=COL_MUTED, font=(self.font_num, 12))
        self.url_lbl.pack(fill="x")

        self._label(body, "PIN 변경 (비워두면 그대로)" if has_pin else f"새 PIN (숫자 {PIN_LEN}자리)")
        self.e_pin = self._entry(body)
        self._label(body, "PIN 확인")
        self.e_pin2 = self._entry(body)

        self.msg = ctk.CTkLabel(body, text="", height=18, anchor="w", font=(self.font_ui, 11))
        self.msg.pack(fill="x", pady=(6, 0))

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill="x", pady=(6, 0))
        if has_pin:
            ctk.CTkButton(btns, text="모든 기기 로그아웃", height=32, corner_radius=6,
                          fg_color=COL_BTN, hover_color=COL_BTN_HOV, text_color=COL_MUTED,
                          font=(self.font_ui, 12), command=self.logout_all
                          ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(btns, text="저장" if running else "저장 후 켜기", height=32, corner_radius=6,
                      fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOV, text_color="#FFFFFF",
                      font=(self.font_ui, 12, "bold"), command=self.save
                      ).pack(side="left", expand=True, fill="x", padx=(4 if has_pin else 0, 0))

        self.bind("<Return>", lambda e: self.save())
        self.after(300, self.e_pin.focus_set)

    def _label(self, parent, text):
        ctk.CTkLabel(parent, text=text, anchor="w", height=18, text_color=COL_SUB,
                     font=(self.font_ui, 11)).pack(fill="x", pady=(12, 4))

    def _entry(self, parent):
        e = ctk.CTkEntry(parent, show="●", height=34, font=(self.font_num, 14),
                         fg_color=COL_CARD, border_color=COL_BORDER, border_width=1, text_color=COL_VALUE)
        e.pack(fill="x")
        return e

    def set_url(self, url):
        """Funnel 주소는 tailscale 명령으로 확인하느라 늦게 채워짐 (MainController가 호출)"""
        if url:
            self.url_lbl.configure(text="  " + url, fg_color=COL_ON_BG, text_color=STATE_COLORS["RUN"][0])
        else:
            self.url_lbl.configure(text="  Funnel 꺼짐 · 사내망/Tailscale로만 접속", text_color=COL_MUTED,
                                   font=(self.font_ui, 11))

    def _show(self, text, ok=False):
        self.msg.configure(text=text, text_color=STATE_COLORS["RUN"][0] if ok else "#FF6961")

    def save(self):
        p1, p2 = self.e_pin.get().strip(), self.e_pin2.get().strip()
        if not p1 and not p2:
            if not self.has_pin:
                return self._show("PIN을 정해주세요")
            pin = None   # PIN은 그대로 두고 켜기만
        elif len(p1) != PIN_LEN or not p1.isdigit():
            return self._show(f"PIN은 숫자 {PIN_LEN}자리예요")
        elif p1 != p2:
            return self._show("PIN 확인이 일치하지 않아요")
        else:
            pin = p1
        self.on_save(pin)
        self.destroy()

    def logout_all(self):
        if messagebox.askyesno("모든 기기 로그아웃", "로그인된 모든 휴대폰에서 로그아웃할까요?\n다시 접속하려면 PIN을 입력해야 해요.",
                               parent=self):
            self.on_logout_all()
            self._show("모든 기기를 로그아웃했어요", ok=True)
