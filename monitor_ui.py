import datetime
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
import customtkinter as ctk

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

        self.init_width = 820

        self.title("DN Solutions Machine Watcher v2.3")
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=COL_BG)

        # [v2.3] 숫자용 폰트: JetBrains Mono 우선, 없으면 Cascadia → Consolas 순으로 대체
        fams = set(tkfont.families(self))
        self.font_num = next((f for f in ["JetBrains Mono", "Cascadia Mono", "Cascadia Code"] if f in fams), "Consolas")
        self.font_ui = "Malgun Gothic"

        self.machines = machines
        self.scroll = None
        self.notify_enabled = tk.BooleanVar(value=True)
        self.widgets = {}
        self.is_hidden = False
        self.is_compact = False

        self.drag_start_x = 0
        self.drag_start_y = 0
        self._is_dragging = False

        self.setup_ui()
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

    def setup_ui(self):
        # 1. 고정 헤더
        self.header = ctk.CTkFrame(self, height=50, corner_radius=0, fg_color=COL_BG)
        self.header.pack(fill="x", side="top")

        self.header_line = ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=COL_BORDER)
        self.header_line.pack(fill="x", side="top")

        self.title_lbl = ctk.CTkLabel(
            self.header,
            text="CNC FACTORY MONITOR",
            font=("Segoe UI", 13, "bold"),
            text_color=COL_MUTED
        )
        self.title_lbl.pack(side="left", padx=20, pady=12)

        self.compact_btn = ctk.CTkButton(
            self.header, text="➖", width=36, height=36,
            fg_color="transparent", hover_color=COL_BTN,
            font=("Segoe UI Emoji", 18),
            command=self.toggle_compact_mode
        )
        self.compact_btn.pack(side="right", padx=(0, 15), pady=7)
        self.compact_tooltip = ToolTip(self.compact_btn, "최소화 모드")

        self.notify_btn = ctk.CTkButton(
            self.header, text="🔔", width=36, height=36,
            fg_color="transparent", hover_color=COL_BTN,
            font=("Segoe UI Emoji", 20),
            command=self.toggle_notify
        )
        self.notify_btn.pack(side="right", padx=(0, 5), pady=7)
        self.notify_tooltip = ToolTip(self.notify_btn, "알림: 켜짐")

        # [v2.2 추가] 장비 설정 버튼 (command는 MainController가 연결)
        self.settings_btn = ctk.CTkButton(
            self.header, text="⚙️", width=36, height=36,
            fg_color="transparent", hover_color=COL_BTN,
            font=("Segoe UI Emoji", 18)
        )
        self.settings_btn.pack(side="right", padx=(0, 5), pady=7)
        self.settings_tooltip = ToolTip(self.settings_btn, "장비 설정")

        # 2. 메인 컨테이너 영역 (장비 카드)
        self.build_machine_cards()

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
                "c_strip": c_strip, "c_time": c_time
            }

            for w_item in [card, comp_f, c_name, c_time, c_strip]:
                w_item.bind("<ButtonPress-1>", self.on_drag_start)
                w_item.bind("<B1-Motion>", self.on_drag_motion)
                w_item.bind("<ButtonRelease-1>", self.on_drag_release)

    # ── [v2.3] 상태를 UI에 일괄 반영 ──────────────────────────
    def apply_status(self, ip, mode, status, tool, cyc, is_alarm, connected):
        w = self.widgets.get(ip)
        if not w: return

        state = state_of(status, is_alarm, connected)
        accent, badge_bg = STATE_COLORS[state]

        if state == "ALARM":     badge_txt = "▲ ALARM"
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

    # ── 알림 토글 로직 ──────────────────────────────────────
    def toggle_notify(self):
        current_state = not self.notify_enabled.get()
        self.notify_enabled.set(current_state)

        if current_state:
            self.notify_btn.configure(text="🔔")
            self.notify_tooltip.text = "알림: 켜짐"
        else:
            self.notify_btn.configure(text="🔕")
            self.notify_tooltip.text = "알림: 꺼짐"
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
            self.overrideredirect(True)

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
            self.overrideredirect(False)

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

    def restore_from_click(self):
        if self.is_compact:
            self.toggle_compact_mode()

    def hide_window(self):
        self.withdraw()
        self.is_hidden = True

    def show_window(self):
        self.deiconify()
        self.is_hidden = False

    def show_emergency_popup(self, machine_name):
        popup = ctk.CTkToplevel(self, fg_color=COL_BG)
        popup.title("ALARM")
        popup.geometry("300x256")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)

        circle = ctk.CTkFrame(popup, width=56, height=56, corner_radius=28, fg_color="#33100D")
        circle.pack(pady=(24, 10))
        circle.pack_propagate(False)
        ctk.CTkLabel(circle, text="⚠", font=("Segoe UI Emoji", 24), text_color="#FF453A").pack(expand=True)

        ctk.CTkLabel(popup, text="ALARM", font=(self.font_ui, 18, "bold"), text_color="#FF453A").pack()
        ctk.CTkLabel(popup, text=machine_name, font=(self.font_ui, 15, "bold"), text_color=COL_TEXT).pack(pady=(2, 0))
        now = datetime.datetime.now().strftime("%H:%M:%S")
        ctk.CTkLabel(popup, text=f"{now} 발생 · 장비 상태를 확인하세요",
                     font=(self.font_ui, 11), text_color=COL_MUTED).pack(pady=(0, 14))
        ctk.CTkButton(popup, text="확인", width=120, height=30, corner_radius=8,
                      fg_color="#33100D", hover_color="#4A1815", text_color="#FF6961",
                      border_width=1, border_color="#6E2420",
                      font=(self.font_ui, 12, "bold"), command=popup.destroy).pack()
        self.bell()


# ── [v2.2 추가] 장비 추가/삭제 설정 창 ──────────────────────────
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, machines_data, on_save):
        super().__init__(master, fg_color=COL_BG)
        self.title("장비 설정")
        self.geometry("520x420")
        self.attributes("-topmost", True)
        self.grab_set()  # 설정 중에는 메인 창 조작 잠금
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
