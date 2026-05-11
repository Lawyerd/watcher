import tkinter as tk
import customtkinter as ctk

class AppUI(ctk.CTk):
    def __init__(self, machines):
        super().__init__()
        self.title("DN Solutions Machine Watcher v1.9")
        self.geometry("1050x650")
        ctk.set_appearance_mode("dark")
        
        self.machines = machines
        self.notify_enabled = tk.BooleanVar(value=True)
        self.widgets = {}
        
        # 창 상태 플래그
        self.is_hidden = False
        
        self.setup_ui()

        # 창 닫기 버튼(X) 클릭 시 hide_window 실행
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

    def setup_ui(self):
        header = ctk.CTkFrame(self, height=70, corner_radius=0, fg_color="#1A1A1A")
        header.pack(fill="x", side="top")
        ctk.CTkLabel(header, text="CNC FACTORY MONITOR", font=("Segoe UI", 24, "bold")).pack(side="left", padx=30)
        ctk.CTkCheckBox(header, text="알림 활성화", variable=self.notify_enabled).pack(side="right", padx=30)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=20, pady=20)

        for m in self.machines:
            card = ctk.CTkFrame(self.scroll, border_width=1, border_color="#333333")
            card.pack(fill="x", pady=10)
            card.grid_columnconfigure(0, weight=0, minsize=280)
            card.grid_columnconfigure((1, 2, 3, 4), weight=1, uniform="metrics")

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.grid(row=0, column=0, rowspan=2, padx=25, pady=20, sticky="nw")
            ctk.CTkLabel(info, text=m.name, font=("Segoe UI", 22, "bold"), anchor="w").pack(fill="x")
            ctk.CTkLabel(info, text=m.ip, text_color="#777777", font=("Consolas", 13), anchor="w").pack(fill="x")
            
            btn = ctk.CTkButton(info, text="연결하기", width=120)
            btn.pack(pady=(15, 0), anchor="w")

            def add_m(col, title):
                ctk.CTkLabel(card, text=title, text_color="#888888", font=("Malgun Gothic", 12)).grid(row=0, column=col, pady=(20, 0))
                lbl = ctk.CTkLabel(card, text="-", font=("Consolas", 32, "bold"), width=180)
                lbl.grid(row=1, column=col, pady=(0, 20))
                return lbl

            self.widgets[m.ip] = {
                "btn": btn, "mode": add_m(1, "MODE"), "status": add_m(2, "STATUS"),
                "tool": add_m(3, "TOOL"), "time": add_m(4, "CYCLE TIME")
            }
        
        self.scroll.bind("<Configure>", lambda e: self.check_scrollbar())

    def hide_window(self):
        """창을 숨기고 플래그 업데이트"""
        self.withdraw()
        self.is_hidden = True

    def show_window(self):
        """창을 다시 표시하고 플래그 업데이트"""
        self.deiconify()
        self.is_hidden = False

    def check_scrollbar(self):
        canvas = self.scroll._parent_canvas
        scrollbar = self.scroll._scrollbar
        content_height = canvas.bbox("all")[3]
        visible_height = canvas.winfo_height()

        if content_height <= visible_height:
            scrollbar.grid_forget()
        else:
            scrollbar.grid(row=0, column=1, sticky="ns")