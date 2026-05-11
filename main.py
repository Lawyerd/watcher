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

# ── 로깅 설정 ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("cnc_watcher.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# ── 중복 실행 방지 ────────────────────────────────────────────
_lock_socket = None

def is_already_running():
    global _lock_socket
    try:
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_socket.bind(("127.0.0.1", 54321))
        return False
    except socket.error:
        return True

# ── 경로 설정 ─────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
DLL_DIR     = os.path.join(BASE_DIR, "dll")
CONFIG_FILE = os.path.join(BASE_DIR, "machines.json")
DLL_PATH    = os.path.join(DLL_DIR, "Fwlib64.dll")

if os.path.exists(DLL_DIR):
    if hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(DLL_DIR)
    os.environ['PATH'] = DLL_DIR + os.pathsep + os.environ['PATH']

# ── 설정 로드 ─────────────────────────────────────────────────
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [
            FanucMachine(m['name'], m['ip'], port=m.get('port', 8193), dll_path=DLL_PATH)
            for m in data
        ]
    except Exception as e:
        logger.error(f"설정 파일 로드 실패: {e}")
        return []

# ── 메인 컨트롤러 ─────────────────────────────────────────────
class MainController:
    def __init__(self):
        self.machines = load_config()
        self.app      = AppUI(self.machines)
        self.notifier = StatusNotifier()

        for m in self.machines:
            if m.ip in self.app.widgets:
                self.app.widgets[m.ip]["btn"].configure(
                    command=lambda target=m: self.toggle_conn(target)
                )

        self.setup_tray()
        self.update_loop()

    def setup_tray(self):
        img = Image.new('RGB', (64, 64), color=(31, 106, 165))
        ImageDraw.Draw(img).rectangle([16, 16, 48, 48], fill=(255, 255, 255))
        menu = (
            pystray.MenuItem('열기',  self.app.show_window, default=True),
            pystray.MenuItem('종료', self.quit_all),
        )
        self.tray_icon = pystray.Icon("CNC Watcher", img, "CNC Watcher", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def quit_all(self):
        self.tray_icon.stop()
        for m in self.machines:
            m.disconnect()
        self.app.quit()

    def toggle_conn(self, m):
        if not m.is_connected:
            if not m.connect():
                messagebox.showwarning("실패", f"[{m.name}] 연결 불가")
        else:
            m.disconnect()
            self.notifier.check_and_notify(
                m.name, "OFFLINE", False, self.app.notify_enabled.get()
            )

    def update_loop(self):
        for m in self.machines:
            w = self.app.widgets.get(m.ip)
            if not w:
                continue

            if m.is_connected:
                # 🔴 수정 5: 광범위한 except 제거 → 연결 오류와 코드 버그를 구분
                # 기존: except: m.is_connected = False  (어떤 에러인지 알 수 없었음)
                try:
                    m.fetch_data()
                except OSError as e:
                    # 네트워크/DLL 통신 오류 → 연결 끊김으로 처리
                    logger.warning(f"[{m.name}] 통신 오류, 연결 해제: {e}")
                    m.is_connected = False
                except Exception as e:
                    # 예상치 못한 코드 버그 → 로그만 남기고 연결 유지
                    logger.error(f"[{m.name}] fetch_data 예외: {e}", exc_info=True)

                if m.is_connected:
                    notif_res = self.notifier.check_and_notify(
                        m.name, m.data["status"], m.data["is_alarm"],
                        self.app.notify_enabled.get()
                    )

                    # 🔴 수정 6: is_hidden 여부와 무관하게 알람 팝업은 항상 표시
                    # (숨김 상태에서도 알람은 사용자에게 알려야 함 - 의도적 동작)
                    if notif_res == "ALARM_POPUP":
                        self.app.show_emergency_popup(m.name)

                    # UI 업데이트는 is_hidden이 False일 때만
                    if not self.app.is_hidden:
                        st  = m.data["status"]
                        cyc = m.data["cycle_time"]

                        st_col = "#F1C40F"
                        if "RUN"  in st: st_col = "#2ECC71"
                        if m.data["is_alarm"]: st_col = "#E74C3C"

                        # 전체 모드 위젯
                        w["mode"].configure(text=m.data["mode"], text_color="#3498DB")
                        w["status"].configure(text=st, text_color=st_col)
                        w["tool"].configure(text=m.data["tool"], text_color="#E67E22")
                        w["time"].configure(text=cyc, text_color=("#FFFFFF", "#FFFFFF"))
                        w["btn"].configure(text="연결 해제", fg_color="#444")

                        # 최소화 모드 위젯
                        w["c_status"].configure(text=st, text_color=st_col)
                        w["c_time"].configure(text=cyc, text_color=("#FFFFFF", "#FFFFFF"))

            else:
                # 비연결 상태 UI
                if not self.app.is_hidden:
                    for k in ["mode", "status", "tool", "c_status"]:
                        w[k].configure(text="-", text_color="#444444")
                    w["time"].configure(text="-",   text_color=("#FFFFFF", "#FFFFFF"))
                    w["c_time"].configure(text="-", text_color=("#FFFFFF", "#FFFFFF"))
                    w["btn"].configure(text="연결하기", fg_color=["#3B8ED0", "#1F6AA5"])

        self.app.after(3000 if self.app.is_hidden else 500, self.update_loop)


if __name__ == "__main__":
    if is_already_running():
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        messagebox.showwarning("알림", "이미 실행 중입니다.")
        r.destroy()
        sys.exit(0)
    MainController().app.mainloop()