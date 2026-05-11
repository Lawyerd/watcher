import os
import sys
import json
import socket
import threading
from tkinter import messagebox
from PIL import Image, ImageDraw
import pystray
from fanuc_logic import FanucMachine
from monitor_ui import AppUI
from notifier import StatusNotifier

_lock_socket = None

def is_already_running():
    global _lock_socket
    try:
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_socket.bind(("127.0.0.1", 54321))
        return False
    except socket.error:
        return True

BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
DLL_DIR = os.path.join(BASE_DIR, "dll")
CONFIG_FILE = os.path.join(BASE_DIR, "machines.json")
DLL_PATH = os.path.join(DLL_DIR, "Fwlib64.dll")

if os.path.exists(DLL_DIR):
    if hasattr(os, 'add_dll_directory'): os.add_dll_directory(DLL_DIR)
    os.environ['PATH'] = DLL_DIR + os.pathsep + os.environ['PATH']

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [FanucMachine(m['name'], m['ip'], port=m.get('port', 8193), dll_path=DLL_PATH) for m in data]
    except: return []

class MainController:
    def __init__(self):
        self.machines = load_config()
        self.app = AppUI(self.machines)
        self.notifier = StatusNotifier()
        for m in self.machines:
            if m.ip in self.app.widgets:
                self.app.widgets[m.ip]["btn"].configure(command=lambda target=m: self.toggle_conn(target))
        self.setup_tray()
        self.update_loop()

    def setup_tray(self):
        img = Image.new('RGB', (64, 64), color=(31, 106, 165))
        ImageDraw.Draw(img).rectangle([16, 16, 48, 48], fill=(255, 255, 255))
        menu = (pystray.MenuItem('열기', self.app.show_window, default=True), pystray.MenuItem('종료', self.quit_all))
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
            self.notifier.check_and_notify(m.name, "OFFLINE", False, self.app.notify_enabled.get())

    def update_loop(self):
        for m in self.machines:
            w = self.app.widgets[m.ip]
            if m.is_connected:
                try:
                    m.fetch_data()
                    notif_res = self.notifier.check_and_notify(m.name, m.data["status"], m.data["is_alarm"], self.app.notify_enabled.get())
                    if notif_res == "ALARM_POPUP": self.app.show_emergency_popup(m.name)

                    if not self.app.is_hidden:
                        st, cyc = m.data["status"], m.data["cycle_time"]
                        st_col = "#F1C40F"
                        if "RUN" in st: st_col = "#2ECC71"
                        if m.data["is_alarm"]: st_col = "#E74C3C"

                        # [1] 일반 모드 위젯 업데이트 (time은 항상 흰색 고정)
                        w["mode"].configure(text=m.data["mode"], text_color="#3498DB")
                        w["status"].configure(text=st, text_color=st_col)
                        w["tool"].configure(text=m.data["tool"], text_color="#E67E22")
                        w["time"].configure(text=cyc, text_color=("#FFFFFF", "#FFFFFF"))
                        w["btn"].configure(text="연결 해제", fg_color="#444")

                        # [2] 최소화 모드 위젯 업데이트 (c_time은 항상 흰색 고정)
                        w["c_status"].configure(text=st, text_color=st_col)
                        w["c_time"].configure(text=cyc, text_color=("#FFFFFF", "#FFFFFF"))

                except: m.is_connected = False
            else:
                if not self.app.is_hidden:
                    # 비연결 상태: time과 c_time은 흰색 유지, 나머지만 #444
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