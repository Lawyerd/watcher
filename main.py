import os
import sys
import json
import socket
import logging
import threading
from tkinter import messagebox
from PIL import Image, ImageDraw
import pystray
from fanuc_logic import FanucMachine
from monitor_ui import AppUI
from notifier import StatusNotifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler("cnc_watcher.log", encoding="utf-8")])
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
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DLL_DIR      = os.path.join(BASE_DIR, "dll")
CONFIG_FILE  = os.path.join(BASE_DIR, "machines.json")
DLL_PATH     = os.path.join(DLL_DIR, "Fwlib64.dll")
ICONS_DIR    = os.path.join(BASE_DIR, "icons")
ICON_PATH    = os.path.join(ICONS_DIR, "watcher_icon.ico")

if os.path.exists(DLL_DIR):
    if hasattr(os, 'add_dll_directory'): os.add_dll_directory(DLL_DIR)
    os.environ['PATH'] = DLL_DIR + os.pathsep + os.environ['PATH']

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [FanucMachine(m['name'], m['ip'], port=m.get('port', 8193), dll_path=DLL_PATH) for m in data]
    except Exception as e:
        logger.error(f"설정 로드 실패: {e}")
        return []

class MainController:
    def __init__(self):
        self._check_create_icon()
        self.machines = load_config()
        
        # [v2.0 수정] 로그 폴더 생성을 위해 BASE_DIR 함께 전달
        self.notifier = StatusNotifier(icon_path=ICON_PATH, base_dir=BASE_DIR)
        self.app      = AppUI(self.machines)

        if os.path.exists(ICON_PATH):
            try: self.app.iconbitmap(ICON_PATH)
            except Exception as e: logger.error(f"아이콘 적용 실패: {e}")

        for m in self.machines:
            if m.ip in self.app.widgets:
                self.app.widgets[m.ip]["btn"].configure(command=lambda target=m: self.toggle_conn(target))

        self.setup_tray()
        self.update_loop()

    def _check_create_icon(self):
        if not os.path.exists(ICON_PATH):
            try:
                os.makedirs(ICONS_DIR, exist_ok=True)
                img = Image.new('RGB', (64, 64), color='#1F6AA5')
                draw = ImageDraw.Draw(img)
                draw.rounded_rectangle((4, 4, 60, 60), fill=None, outline='white', width=3, radius=10)
                draw.polygon([(20, 20), (28, 45), (32, 30), (36, 45), (44, 20), (40, 20), (36, 35), (32, 25), (28, 35), (24, 20)], fill='white')
                img.save(ICON_PATH, format='ICO', sizes=[(64, 64), (32, 32), (16, 16)])
            except Exception as e: logger.error(f"아이콘 생성 실패: {e}")

    def setup_tray(self):
        if os.path.exists(ICON_PATH):
            try: img = Image.open(ICON_PATH)
            except Exception:
                img = Image.new('RGB', (64, 64), color=(31, 106, 165))
                ImageDraw.Draw(img).rectangle([16, 16, 48, 48], fill=(255, 255, 255))
        else:
            img = Image.new('RGB', (64, 64), color=(31, 106, 165))
            ImageDraw.Draw(img).rectangle([16, 16, 48, 48], fill=(255, 255, 255))
        
        def safe_show(icon, item): self.app.after(0, self.app.show_window)
        def safe_quit(icon, item): self.app.after(0, self.quit_all)

        menu = (pystray.MenuItem('열기', safe_show, default=True), pystray.MenuItem('종료', safe_quit))
        self.tray_icon = pystray.Icon("CNC Watcher", img, "CNC Watcher", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def quit_all(self):
        self.tray_icon.stop()
        for m in self.machines: m.disconnect()
        self.app.quit()

    def toggle_conn(self, m):
        if not m.is_connected:
            if not m.connect(): messagebox.showwarning("실패", f"[{m.name}] 연결 불가")
        else:
            m.disconnect()
            # [v2.0 수정] 빈 사이클 타임 전달
            self.notifier.check_and_notify(m.name, "OFFLINE", "00:00:00", False, self.app.notify_enabled.get())

    def update_loop(self):
        for m in self.machines:
            w = self.app.widgets.get(m.ip)
            if not w: continue

            if m.is_connected:
                try: m.fetch_data()
                except OSError as e: m.is_connected = False
                except Exception as e: logger.error(f"fetch_data 예외: {e}", exc_info=True)

                if m.is_connected:
                    st  = m.data["status"]
                    cyc = m.data["cycle_time"]
                    
                    # [v2.0 수정] cycle_time을 파라미터로 추가 전달
                    notif_res = self.notifier.check_and_notify(
                        m.name, st, cyc, m.data["is_alarm"], self.app.notify_enabled.get()
                    )

                    if notif_res == "ALARM_POPUP": self.app.show_emergency_popup(m.name)

                    if not self.app.is_hidden:
                        st_col = "#F1C40F"
                        if "RUN"  in st: st_col = "#2ECC71"
                        if m.data["is_alarm"]: st_col = "#E74C3C"

                        w["mode"].configure(text=m.data["mode"], text_color="#3498DB")
                        w["status"].configure(text=st, text_color=st_col)
                        w["tool"].configure(text=m.data["tool"], text_color="#E67E22")
                        w["time"].configure(text=cyc, text_color=("#FFFFFF", "#FFFFFF"))
                        w["btn"].configure(text="연결 해제", fg_color="#444")
                        w["c_status"].configure(text=st, text_color=st_col)
                        w["c_time"].configure(text=cyc, text_color=("#FFFFFF", "#FFFFFF"))
            else:
                if not self.app.is_hidden:
                    for k in ["mode", "status", "tool", "c_status"]:
                        w[k].configure(text="-", text_color="#444444")
                    w["time"].configure(text="-", text_color=("#FFFFFF", "#FFFFFF"))
                    w["c_time"].configure(text="-", text_color=("#FFFFFF", "#FFFFFF"))
                    w["btn"].configure(text="연결하기", fg_color=["#3B8ED0", "#1F6AA5"])

        self.app.after(3000 if self.app.is_hidden else 500, self.update_loop)

if __name__ == "__main__":
    if is_already_running():
        import tkinter as tk
        r = tk.Tk(); r.withdraw(); messagebox.showwarning("알림", "이미 실행 중입니다."); r.destroy(); sys.exit(0)
    MainController().app.mainloop()