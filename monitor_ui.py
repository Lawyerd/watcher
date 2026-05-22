import tkinter as tk
import customtkinter as ctk

class AppUI(ctk.CTk):
    def __init__(self, machines):
        super().__init__()
        self.init_width  = 1050
        self.init_height = 650
        self.title("DN Solutions Machine Watcher v2.0")
        self.geometry(f"{self.init_width}x{self.init_height}")
        ctk.set_appearance_mode("dark")

        self.machines       = machines
        self.notify_enabled = tk.BooleanVar(value=True)
        self.widgets        = {}
        self.is_hidden      = False
        self.is_compact     = False

        # 타이틀바 없는 창 드래그용
        self._drag_x = 0
        self._drag_y = 0

        self.setup_ui()
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

    # ── 메트릭 라벨 생성 헬퍼 ─────────────────────────────────
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

    # ── 스크롤 영역 구성 (Canvas 방식) ───────────────────────
    def _build_scroll_area(self):
        """Canvas + Scrollbar 조합.
        내용이 창보다 짧으면 스크롤바 숨김, 길어지면 자동으로 표시."""

        self.scroll_outer = tk.Frame(self, bg="#212121")
        self.scroll_outer.pack(fill="both", expand=True, padx=10, pady=10)

        self._scrollbar = ctk.CTkScrollbar(self.scroll_outer, orientation="vertical")
        self._canvas    = tk.Canvas(
            self.scroll_outer,
            bg="#212121", highlightthickness=0,
            yscrollcommand=self._on_scroll_update,
        )
        self._scrollbar.configure(command=self._canvas.yview)

        # 스크롤바는 처음엔 pack 안 함 — 내용 넘칠 때만 표시
        self._canvas.pack(side="left", fill="both", expand=True)

        # canvas 안에 카드들이 들어갈 내부 프레임
        self.scroll = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self.scroll, anchor="nw"
        )

        self.scroll.bind("<Configure>",   self._on_frame_configure)
        self._canvas.bind("<Configure>",  self._on_canvas_configure)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scroll.bind("<MouseWheel>",  self._on_mousewheel)

    def _on_scroll_update(self, first, last):
        """스크롤바 위치 갱신 + 필요 여부에 따라 표시/숨김."""
        self._scrollbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self._scrollbar.pack_forget()        # 내용이 창 안에 다 들어감 → 숨김
        else:
            self._scrollbar.pack(side="right", fill="y")  # 넘침 → 표시

    def _on_frame_configure(self, event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        # 캔버스 너비에 맞게 내부 프레임 너비 조정
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ── UI 구성 ───────────────────────────────────────────────
    def setup_ui(self):
        # 1. 고정 헤더
        self.header = ctk.CTkFrame(self, height=60, corner_radius=0, fg_color="#1A1A1A")
        self.header.pack(fill="x", side="top")

        self.title_lbl = ctk.CTkLabel(
            self.header, text="CNC FACTORY MONITOR",
            font=("Segoe UI", 20, "bold")
        )
        self.title_lbl.pack(side="left", padx=20)

        self.compact_btn = ctk.CTkButton(
            self.header, text="최소화", width=70, height=28,
            fg_color="#333", hover_color="#444",
            command=self.toggle_compact_mode
        )
        self.compact_btn.pack(side="right", padx=10)

        self.check_box = ctk.CTkCheckBox(
            self.header, text="알림 활성화",
            variable=self.notify_enabled, font=("", 12)
        )
        self.check_box.pack(side="right", padx=10)

        # 2. 스크롤 영역 (필요할 때만 스크롤바 표시)
        self._build_scroll_area()

        # 3. 카드 생성
        for m in self.machines:
            card = ctk.CTkFrame(self.scroll, border_width=1, border_color="#333333")
            card.pack(fill="x", pady=5)

            # [A] 전체 모드 컨테이너
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

            # [B] 최소화 모드 컨테이너
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
                "c_status": c_status, "c_time": c_time,
            }

            # 카드 위에서도 마우스 휠 + 클릭 복원 동작
            # (compact 위젯의 클릭 복원은 _drag_release에서 처리)
            for w in [card, full_f, comp_f, c_name, c_status, c_time]:
                w.bind("<MouseWheel>", self._on_mousewheel)
            for w in [card, full_f, c_name]:
                w.bind("<Button-1>", lambda e: self.restore_from_click())

    # ── 타이틀바 없는 창 드래그 ──────────────────────────────
    def _drag_start(self, event):
        self._drag_x     = event.x_root - self.winfo_x()
        self._drag_y     = event.y_root - self.winfo_y()
        self._drag_moved = False          # 이번 클릭이 드래그였는지 추적

    def _drag_move(self, event):
        self._drag_moved = True
        self.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    def _drag_release(self, event):
        # 드래그 없이 클릭만 했으면 복원
        if not self._drag_moved:
            self.restore_from_click()

    def _bind_drag(self, widget):
        widget.bind("<ButtonPress-1>",  self._drag_start,   add="+")
        widget.bind("<B1-Motion>",      self._drag_move,    add="+")
        widget.bind("<ButtonRelease-1>", self._drag_release, add="+")

    # ── 최소화 모드 토글 ──────────────────────────────────────
    def toggle_compact_mode(self):
        if not self.is_compact:
            self.is_compact = True
            self.attributes("-topmost", True)
            self.overrideredirect(True)          # 타이틀바 제거
            self.header.pack_forget()
            for ip, w in self.widgets.items():
                w["full_f"].pack_forget()
                w["comp_f"].pack(fill="x")

            self.after(50, self._apply_compact_geometry)
        else:
            self.is_compact = False
            self.overrideredirect(False)         # 타이틀바 복원
            self.attributes("-topmost", False)
            self.geometry(f"{self.init_width}x{self.init_height}")

            self.scroll_outer.pack_forget()
            self.header.pack(fill="x", side="top")
            self.scroll_outer.pack(fill="both", expand=True, padx=10, pady=10)

            for ip, w in self.widgets.items():
                w["comp_f"].pack_forget()
                w["full_f"].pack(fill="x")

    def _apply_compact_geometry(self):
        """최소화 모드: 카드 실측 높이로 창 크기를 딱 맞게 설정."""
        self.update_idletasks()

        total_h = 0
        for ip, w in self.widgets.items():
            card_h   = w["card"].winfo_height()
            total_h += card_h if card_h > 1 else 50

        n        = len(self.machines)
        total_h += (n * 10) + 20
        total_h  = max(total_h, 60)

        self.geometry(f"360x{total_h}")

        # 타이틀바가 없으므로 카드 전체를 드래그 핸들로 사용
        for ip, w in self.widgets.items():
            for widget in [w["card"], w["comp_f"], w["c_status"], w["c_time"]]:
                self._bind_drag(widget)

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