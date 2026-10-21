import ctypes
import datetime
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
import customtkinter as ctk
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
COL_REMOTE_ON  = "#0E2E1A"   # [v2.4] 원격 모니터링 켜짐 버튼 배경
COL_ALM_CODE   = "#FF6961"   # [v2.4] 알람 목록: 번호
COL_ALM_MSG    = "#F2C9C6"   #        내용
COL_ALM_SUB    = "#8E5A56"   #        발생 시각
COL_ALM_LINE   = "#3A1B18"   #        구분선

# [v2.4] 헤더 아이콘 글리프 (Segoe Fluent Icons / MDL2 Assets 공통 코드)
ICON_SETTINGS = ""
ICON_BELL     = ""
ICON_BELL_OFF = ""
ICON_COMPACT  = ""
ICON_REMOTE   = ""
ICON_MINIMIZE = ""
ICON_CLOSE    = ""

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
            badge = ctk.CTkLabel(row1, text="OFFLINE", font=(self.font_ui, 11, "bold"),
                                 text_color=STATE_COLORS["OFFLINE"][0],
                                 fg_color=STATE_COLORS["OFFLINE"][1],
                                 corner_radius=11, width=86, height=24)
            badge.pack(side="right")

            row2 = ctk.CTkFrame(body, fg_color="transparent")
            row2.pack(fill="x", pady=(10, 0))
            btn = ctk.CTkButton(row2, text="연결하기", width=84, height=26, corner_radius=6,
                                fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOV,
                                text_color="#FFFFFF", font=(self.font_ui, 11, "bold"))
            btn.pack(side="left")

            metric_vals = {}
            for lbl, key in (("MODE", "mode"), ("TOOL", "tool")):
                ctk.CTkLabel(row2, text=lbl, font=(self.font_ui, 10), text_color=COL_SUB).pack(side="left", padx=(20, 5))
                v = ctk.CTkLabel(row2, text="-", font=(self.font_num, 14), text_color=COL_SUB)
                v.pack(side="left")
                metric_vals[key] = v

            time_l = ctk.CTkLabel(row2, text="-", font=(self.font_num, 22, "bold"), text_color=COL_SUB)
            time_l.pack(side="right")

            # [v2.4] 알람 목록 (C안) — 알람일 때만 _render_alarms가 채워서 pack
            alm_f = ctk.CTkFrame(body, fg_color="transparent", height=10)

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
                "mode": metric_vals["mode"], "tool": metric_vals["tool"], "time": time_l,
                "c_strip": c_strip, "c_time": c_time,
                "alm_f": alm_f, "alm_key": ()
            }

            for w_item in [card, comp_f, c_name, c_time, c_strip]:
                w_item.bind("<ButtonPress-1>", self.on_drag_start)
                w_item.bind("<B1-Motion>", self.on_drag_motion)
                w_item.bind("<ButtonRelease-1>", self.on_drag_release)

    # ── [v2.3] 상태를 UI에 일괄 반영 ──────────────────────────
    def apply_status(self, ip, mode, status, tool, cyc, is_alarm, connected, alarms=()):
        w = self.widgets.get(ip)
        if not w: return

        state = state_of(status, is_alarm, connected)
        accent, badge_bg = STATE_COLORS[state]

        # [v2.4] 알람 목록은 내용이 바뀔 때만 다시 그림 (0.5초마다 위젯 재생성 방지)
        alarms = alarms if state == "ALARM" else ()
        key = tuple((a["code"], a["msg"]) for a in alarms)
        if key != w["alm_key"]:
            w["alm_key"] = key
            self._render_alarms(w["alm_f"], alarms)
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

        t_col = accent if state == "ALARM" else (COL_TEXT if connected else COL_SUB)
        t_txt = cyc if connected else "-"
        w["time"].configure(text=t_txt, text_color=t_col)
        w["c_time"].configure(text=t_txt, text_color=t_col)

        if connected:
            w["btn"].configure(text="연결 해제", fg_color=COL_BTN, hover_color=COL_BTN_HOV, text_color=COL_MUTED)
        else:
            w["btn"].configure(text="연결하기", fg_color=COL_ACCENT, hover_color=COL_ACCENT_HOV, text_color="#FFFFFF")

    def _render_alarms(self, frame, alarms):
        for child in frame.winfo_children():
            child.destroy()
        if not alarms:
            frame.pack_forget()
            return

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
        frame.pack(fill="x", pady=(10, 0))

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

        if current_state:
            self.notify_btn.configure(text=ICON_BELL)
            self.notify_tooltip.text = "알림: 켜짐"
        else:
            self.notify_btn.configure(text=ICON_BELL_OFF)
            self.notify_tooltip.text = "알림: 꺼짐"

    # ── [v2.4] 원격 모니터링 버튼 상태 표시 ──────────────────
    def set_remote_state(self, on, urls=()):
        if on:
            self.remote_btn.configure(fg_color=COL_REMOTE_ON, hover_color=COL_REMOTE_ON,
                                      text_color=STATE_COLORS["RUN"][0])
            self.remote_tooltip.text = "원격 모니터링: 켜짐 (절전 차단 중)\n" + "\n".join(urls) + "\n우클릭: 설정"
        else:
            self.remote_btn.configure(fg_color="transparent", hover_color=COL_BTN, text_color=COL_MUTED)
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
            self.url_lbl.configure(text="  " + url, fg_color=COL_REMOTE_ON, text_color=STATE_COLORS["RUN"][0])
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
