import tkinter as tk
import customtkinter as ctk

class AppUI(ctk.CTk):
    def __init__(self, machines):
        super().__init__()
        self.init_width = 1050
        self.init_height = 650
        self.title("DN Solutions Machine Watcher v1.9")
        self.geometry(f"{self.init_width}x{self.init_height}")
        ctk.set_appearance_mode("dark")
        
        self.machines = machines
        self.notify_enabled = tk.BooleanVar(value=True)
        self.widgets = {}
        self.is_hidden = False
        self.is_compact = False 
        
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
        self.header = ctk.CTkFrame(self, height=60, corner_radius=0, fg_color="#1A1A1A")
        self.header.pack(fill="x", side="top")
        
        self.title_lbl = ctk.CTkLabel(self.header, text="CNC FACTORY MONITOR", font=("Segoe UI", 20, "bold"))
        self.title_lbl.pack(side="left", padx=20)
        
        self.compact_btn = ctk.CTkButton(
            self.header, text="최소화", width=70, height=28,
            fg_color="#333", hover_color="#444",
            command=self.toggle_compact_mode
        )
        self.compact_btn.pack(side="right", padx=10)

        self.check_box = ctk.CTkCheckBox(self.header, text="알림 활성화", variable=self.notify_enabled, font=("", 12))
        self.check_box.pack(side="right", padx=10)

        # 2. 메인 스크롤 영역
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)

        for m in self.machines:
            card = ctk.CTkFrame(self.scroll, border_width=1, border_color="#333333")
            card.pack(fill="x", pady=5)

            # --- [A] 전체 모드용 컨테이너 ---
            full_f = ctk.CTkFrame(card, fg_color="#1E1E1E")
            full_f.pack(fill="x")
            full_f.grid_columnconfigure(0, weight=0, minsize=200)
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

            c_name = ctk.CTkLabel(comp_f, text=m.name, font=("Segoe UI", 12, "bold"))
            c_name.grid(row=0, column=0, padx=15, pady=10, sticky="w")
            
            c_status = ctk.CTkLabel(comp_f, text="-", font=("Consolas", 13, "bold"))
            c_status.grid(row=0, column=1, pady=10)
            
            c_time = ctk.CTkLabel(
                comp_f, text="-",
                font=("Consolas", 13, "bold"),
                text_color=("#FFFFFF", "#FFFFFF")
            )
            c_time.grid(row=0, column=2, pady=10)

            # 위젯 참조 저장
            self.widgets[m.ip] = {
                "card": card, "full_f": full_f, "comp_f": comp_f, "btn": btn,
                "mode": v_mode, "status": v_status, "tool": v_tool, "time": v_time,
                "c_status": c_status, "c_time": c_time
            }

            for w in [card, comp_f, c_name, c_status, c_time]:
                w.bind("<Button-1>", lambda e: self.restore_from_click())

    def toggle_compact_mode(self):
        if not self.is_compact:
            self.is_compact = True
            h = 10 + (len(self.machines) * 50)
            self.geometry(f"360x{int(h)}")
            self.attributes("-topmost", True)
            self.header.pack_forget()
            for ip, w in self.widgets.items():
                w["full_f"].pack_forget()
                w["comp_f"].pack(fill="x")
        else:
            self.is_compact = False
            self.geometry(f"{self.init_width}x{self.init_height}")
            self.attributes("-topmost", False)
            self.header.pack(fill="x", side="top")
            self.scroll.pack(fill="both", expand=True, padx=10, pady=10)
            for ip, w in self.widgets.items():
                w["comp_f"].pack_forget()
                w["full_f"].pack(fill="x")

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