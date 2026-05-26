import tkinter as tk
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
        calc_height = 120 + (len(machines) * 130)
        self.init_height = max(300, min(850, calc_height)) 
        
        self.needs_scroll = calc_height > 850 
        
        self.title("DN Solutions Machine Watcher v2.0")
        self.geometry(f"{self.init_width}x{self.init_height}")
        self.minsize(self.init_width, self.init_height)
        
        ctk.set_appearance_mode("dark")
        
        self.machines = machines
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

        # 2. 메인 컨테이너 영역
        if self.needs_scroll:
            self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        else:
            self.scroll = ctk.CTkFrame(self, fg_color="transparent")
            
        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)

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