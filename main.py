import os
import sys
import json
import threading
from PIL import Image, ImageDraw
import pystray
from fanuc_logic import FanucMachine
from monitor_ui import AppUI
from notifier import StatusNotifier

# EXE 실행 시와 스크립트 실행 시의 기본 경로를 잡는 함수
def resource_path(relative_path):
    try:
        # PyInstaller에 의해 임시 폴더(_MEIxxxx)가 생성된 경우
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# 설정 및 경로 (EXE와 같은 위치에 둘 파일들)
BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
DLL_DIR = os.path.join(BASE_DIR, "dll")
CONFIG_FILE = os.path.join(BASE_DIR, "machines.json")
DLL_PATH = os.path.join(DLL_DIR, "Fwlib64.dll")

# DLL 환경 변수 추가
if os.path.exists(DLL_DIR):
    if hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(DLL_DIR)
    os.environ['PATH'] = DLL_DIR + os.pathsep + os.environ['PATH']

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [FanucMachine(m['name'], m['ip'], dll_path=DLL_PATH) for m in data]
    except Exception as e:
        print(f"설정 로드 실패: {e}")
        return []

class MainController:
    def __init__(self):
        self.machines = load_config()
        self.app = AppUI(self.machines)
        self.notifier = StatusNotifier()
        
        for m in self.machines:
            if m.ip in self.app.widgets:
                w = self.app.widgets[m.ip]
                w["btn"].configure(command=lambda target=m: self.toggle_conn(target))
        
        self.setup_tray()
        self.update_loop()

    def setup_tray(self):
        image = Image.new('RGB', (64, 64), color=(31, 106, 165))
        dc = ImageDraw.Draw(image)
        dc.rectangle([16, 16, 48, 48], fill=(255, 255, 255))
        
        menu = (
            pystray.MenuItem('열기', self.app.show_window, default=True),
            pystray.MenuItem('종료', self.quit_all)
        )
        self.tray_icon = pystray.Icon("CNC Watcher", image, "CNC Watcher", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def quit_all(self):
        self.tray_icon.stop()
        for m in self.machines:
            m.disconnect()
        self.app.quit()

    def toggle_conn(self, m):
        if not m.is_connected:
            if not m.connect():
                from tkinter import messagebox
                messagebox.showwarning("실패", f"[{m.name}] 연결 불가")
        else:
            m.disconnect()
            self.notifier.check_and_notify(m.name, "OFFLINE", False, self.app.notify_enabled.get())

    def update_loop(self):
        for m in self.machines:
            w = self.app.widgets[m.ip]
            if m.is_connected:
                try:
                    m.fetch_data()
                    self.notifier.check_and_notify(
                        m.name, m.data["status"], m.data["is_alarm"], self.app.notify_enabled.get()
                    )

                    if not self.app.is_hidden:
                        w["mode"].configure(text=m.data["mode"], text_color="#3498DB")
                        st = m.data["status"]
                        st_col = "#F1C40F"
                        if "RUN" in st: st_col = "#2ECC71"
                        if m.data["is_alarm"]: st_col = "#E74C3C"
                        
                        w["status"].configure(text=st, text_color=st_col)
                        w["tool"].configure(text=m.data["tool"], text_color="#E67E22")
                        w["time"].configure(text=m.data["cycle_time"])
                        w["btn"].configure(text="연결 해제", fg_color="#444")
                except:
                    m.is_connected = False
            else:
                if not self.app.is_hidden:
                    for k in ["mode", "status", "tool", "time"]:
                        w[k].configure(text="-", text_color="#444")
                    w["btn"].configure(text="연결하기", fg_color=["#3B8ED0", "#1F6AA5"])
        
        next_delay = 3000 if self.app.is_hidden else 500
        self.app.after(next_delay, self.update_loop)

if __name__ == "__main__":
    controller = MainController()
    controller.app.mainloop()