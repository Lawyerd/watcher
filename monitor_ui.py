import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

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

        self.title("DN Solutions Machine Watcher v2.0")

        ctk.set_appearance_mode("dark")

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

    def _create_metric(self, parent, col, title):
        if title == "TIME":
            t_color = ("#FFFFFF", "#FFFFFF")
            v_color = ("#FFFFFF", "#FFFFFF")
        else:
            t_color = ("#888888", "#888888")
            v_color = ("#DCE4EE", "#DCE4EE")

        t = ctk.CTkLabel(parent, text=title, text_color=t_color, font=("Malgun Gothic", 10))
        t.grid(row=0, column=col, pady=(10, 0))

        v = ctk.CTkLabel(parent, text="-", font=("Consolas", 24, "bold"), text_color=v_color)
        v.grid(row=1, column=col, pady=(0, 10))
        return v

    def setup_ui(self):
        # 1. 고정 헤더
        self.header = ctk.CTkFrame(self, height=50, corner_radius=0, fg_color="#181818")
        self.header.pack(fill="x", side="top")
        
        self.header_line = ctk.CTkFrame(self, height=2, corner_radius=0, fg_color="#1F6AA5")
        self.header_line.pack(fill="x", side="top")
        
        self.title_lbl = ctk.CTkLabel(
            self.header, 
            text="■ CNC FACTORY MONITOR", 
            font=("Segoe UI", 16, "bold"), 
            text_color="#E0E0E0"
        )
        self.title_lbl.pack(side="left", padx=20, pady=12)
        
        # 🚀 [수정] 최소화 버튼을 이모지(➖)로 변경 및 툴팁 연동 (가장 오른쪽에 배치)
        self.compact_btn = ctk.CTkButton(
            self.header, text="➖", width=36, height=36,
            fg_color="transparent", hover_color="#2A2A2A",
            font=("Segoe UI Emoji", 18),
            command=self.toggle_compact_mode
        )
        self.compact_btn.pack(side="right", padx=(0, 15), pady=7)
        self.compact_tooltip = ToolTip(self.compact_btn, "최소화 모드")

        # 🚀 [수정] 알림 토글 버튼을 최소화 버튼 바로 왼쪽에 나란히 배치
        self.notify_btn = ctk.CTkButton(
            self.header, text="🔔", width=36, height=36,
            fg_color="transparent", hover_color="#2A2A2A",
            font=("Segoe UI Emoji", 20),
            command=self.toggle_notify
        )
        self.notify_btn.pack(side="right", padx=(0, 5), pady=7)
        self.notify_tooltip = ToolTip(self.notify_btn, "알림: 켜짐")

        # 🚀 [v2.2 추가] 장비 설정 버튼 (command는 MainController가 연결)
        self.settings_btn = ctk.CTkButton(
            self.header, text="⚙️", width=36, height=36,
            fg_color="transparent", hover_color="#2A2A2A",
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

        calc_height = 120 + (len(self.machines) * 130)
        self.init_height = max(300, min(850, calc_height))
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
            card = ctk.CTkFrame(self.scroll, border_width=1, border_color="#333333")
            card.pack(fill="x", pady=5)

            # --- [A] 전체 모드용 컨테이너 ---
            full_f = ctk.CTkFrame(card, fg_color="#1E1E1E")
            full_f.pack(fill="x")
            
            full_f.grid_columnconfigure(0, weight=0, minsize=160)
            full_f.grid_columnconfigure((1, 2, 3, 4), weight=1)

            info_f = ctk.CTkFrame(full_f, fg_color="transparent")
            info_f.grid(row=0, column=0, rowspan=2, padx=15, pady=10, sticky="nw")
            name_l = ctk.CTkLabel(info_f, text=m.name, font=("Segoe UI", 18, "bold"), anchor="w")
            name_l.pack(fill="x")
            ip_l = ctk.CTkLabel(info_f, text=m.ip, text_color="#777777", font=("Consolas", 11), anchor="w")
            ip_l.pack(fill="x")
            btn = ctk.CTkButton(info_f, text="연결하기", width=100, height=28)
            btn.pack(pady=(10, 0), anchor="w")

            v_mode   = self._create_metric(full_f, 1, "MODE")
            v_status = self._create_metric(full_f, 2, "STATUS")
            v_tool   = self._create_metric(full_f, 3, "TOOL")
            v_time   = self._create_metric(full_f, 4, "TIME")

            # --- [B] 최소화 모드용 컨테이너 ---
            comp_f = ctk.CTkFrame(card, fg_color="#1E1E1E", height=40)
            
            comp_f.grid_columnconfigure(0, weight=0, minsize=100) 
            comp_f.grid_columnconfigure(1, weight=1)
            comp_f.grid_columnconfigure(2, weight=1)

            c_name = ctk.CTkLabel(comp_f, text=m.name, font=("Segoe UI", 14, "bold"))
            c_name.grid(row=0, column=0, padx=(15, 5), pady=10, sticky="w")
            
            c_status = ctk.CTkLabel(comp_f, text="-", font=("Consolas", 16, "bold"))
            c_status.grid(row=0, column=1, pady=10)
            
            c_time = ctk.CTkLabel(
                comp_f, text="-",
                font=("Consolas", 18, "bold"),
                text_color=("#FFFFFF", "#FFFFFF")
            )
            c_time.grid(row=0, column=2, padx=(5, 15), pady=10, sticky="e")

            self.widgets[m.ip] = {
                "card": card, "full_f": full_f, "comp_f": comp_f, "btn": btn,
                "mode": v_mode, "status": v_status, "tool": v_tool, "time": v_time,
                "c_status": c_status, "c_time": c_time
            }

            for w_item in [card, comp_f, c_name, c_status, c_time]:
                w_item.bind("<ButtonPress-1>", self.on_drag_start)
                w_item.bind("<B1-Motion>", self.on_drag_motion)
                w_item.bind("<ButtonRelease-1>", self.on_drag_release)

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
            
            h = 30 + (len(self.machines) * 55)
            w = 300
            
            self.minsize(w, int(h)) 
            self.geometry(f"{w}x{int(h)}")
            self.attributes("-topmost", True)
            self.overrideredirect(True)
            
            self.header.pack_forget()
            for ip, w_ref in self.widgets.items():
                w_ref["full_f"].pack_forget()
                w_ref["comp_f"].pack(fill="x")
        else:
            self.is_compact = False
            self.overrideredirect(False)
            
            self.minsize(self.init_width, self.init_height)
            self.geometry(f"{self.init_width}x{self.init_height}")
            self.attributes("-topmost", False)
            
            self.scroll.pack_forget()
            self.header.pack(fill="x", side="top")
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
        popup = ctk.CTkToplevel(self)
        popup.title("ALARM")
        popup.geometry("300x200")
        popup.attributes("-topmost", True)
        popup.configure(fg_color="#2C0000")
        ctk.CTkLabel(
            popup,
            text=f"⚠️ {machine_name}\nALARM!",
            font=("", 18, "bold"),
            text_color=("#FF4444", "#FF4444")
        ).pack(pady=20)
        ctk.CTkButton(popup, text="확인", width=80, command=popup.destroy).pack()
        self.bell()


# ── [v2.2 추가] 장비 추가/삭제 설정 창 ──────────────────────────
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, machines_data, on_save):
        super().__init__(master)
        self.title("장비 설정")
        self.geometry("520x420")
        self.attributes("-topmost", True)
        self.grab_set()  # 설정 중에는 메인 창 조작 잠금
        self.on_save = on_save
        self.rows = []

        # 컬럼 헤더
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=15, pady=(15, 0))
        for text, w in [("장비명", 140), ("IP 주소", 160), ("포트", 80)]:
            ctk.CTkLabel(head, text=text, width=w, anchor="w",
                         text_color="#888888", font=("Malgun Gothic", 11)).pack(side="left", padx=5)

        # 장비 목록 영역
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        for m in machines_data:
            self.add_row(m["name"], m["ip"], str(m.get("port", 8193)))

        # 하단 버튼
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=15, pady=(0, 15))
        ctk.CTkButton(bottom, text="＋ 장비 추가", width=110,
                      fg_color="#2A2A2A", hover_color="#3A3A3A",
                      command=lambda: self.add_row()).pack(side="left")
        ctk.CTkButton(bottom, text="저장", width=90, command=self.save).pack(side="right")
        ctk.CTkButton(bottom, text="취소", width=90,
                      fg_color="#444444", hover_color="#555555",
                      command=self.destroy).pack(side="right", padx=(0, 8))

    def add_row(self, name="", ip="", port="8193"):
        row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        row.pack(fill="x", pady=3)

        e_name = ctk.CTkEntry(row, width=140, placeholder_text="예: DVF5000")
        e_name.pack(side="left", padx=5)
        e_ip = ctk.CTkEntry(row, width=160, placeholder_text="예: 192.168.10.109")
        e_ip.pack(side="left", padx=5)
        e_port = ctk.CTkEntry(row, width=80)
        e_port.pack(side="left", padx=5)

        if name: e_name.insert(0, name)
        if ip:   e_ip.insert(0, ip)
        e_port.insert(0, port)

        del_btn = ctk.CTkButton(row, text="✕", width=32, height=28,
                                fg_color="#5A2A2A", hover_color="#7A3A3A",
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