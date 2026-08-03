import os
import sys
import json
import time
import socket
import logging
import threading
from tkinter import messagebox
from PIL import Image, ImageDraw
import pystray
from fanuc_logic import FanucMachine
from monitor_ui import AppUI, SettingsDialog
from notifier import StatusNotifier

from logging.handlers import RotatingFileHandler
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    handlers=[logging.StreamHandler(),
                              RotatingFileHandler("cnc_watcher.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")])
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
ICON_PNG     = os.path.join(ICONS_DIR, "watcher_icon.png")   # 토스트 알림용 (winotify는 png 필요)

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
        self.notifier = StatusNotifier(icon_path=ICON_PNG, base_dir=BASE_DIR)
        self.app      = AppUI(self.machines)

        if os.path.exists(ICON_PATH):
            try: self.app.iconbitmap(ICON_PATH)
            except Exception as e: logger.error(f"아이콘 적용 실패: {e}")

        self._bind_conn_buttons()
        self.app.settings_btn.configure(command=self.open_settings)

        self.setup_tray()
        self.update_loop()

    def _bind_conn_buttons(self):
        for m in self.machines:
            if m.ip in self.app.widgets:
                self.app.widgets[m.ip]["btn"].configure(command=lambda target=m: self.toggle_conn(target))

    def open_settings(self):
        data = [{"name": m.name, "ip": m.ip, "port": m.port} for m in self.machines]
        SettingsDialog(self.app, data, self.apply_machine_config)

    def apply_machine_config(self, new_data):
        """설정 창에서 저장 시 호출: machines.json 갱신 후 재시작 없이 즉시 반영"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"설정 저장 실패: {e}")
            messagebox.showerror("저장 실패", f"machines.json 저장 중 오류가 발생했습니다.\n{e}")
            return

        # IP/포트가 같은 장비는 기존 객체를 재사용해 연결 상태 유지
        old_by_key = {(m.ip, m.port): m for m in self.machines}
        new_machines = []
        for entry in new_data:
            key = (entry["ip"], entry["port"])
            if key in old_by_key:
                m = old_by_key.pop(key)
                m.name = entry["name"]
            else:
                m = FanucMachine(entry["name"], entry["ip"], port=entry["port"], dll_path=DLL_PATH)
            new_machines.append(m)

        # 목록에서 빠진 장비는 연결 해제
        for m in old_by_key.values():
            m.want_connected = False
            if m.is_connected: m.disconnect()

        self.machines = new_machines
        self.app.machines = new_machines
        self.app.build_machine_cards()
        self._bind_conn_buttons()
        logger.info(f"장비 설정 변경 적용: {[m.name for m in new_machines]}")

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
        # 토스트용 PNG 버전이 없으면 ico에서 변환 생성
        if os.path.exists(ICON_PATH) and not os.path.exists(ICON_PNG):
            try: Image.open(ICON_PATH).save(ICON_PNG, format='PNG')
            except Exception as e: logger.error(f"PNG 아이콘 생성 실패: {e}")

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
            if m.connect():
                m.want_connected = True
            else:
                messagebox.showwarning("실패", f"[{m.name}] 연결 불가")
        else:
            m.want_connected = False
            m.disconnect()
            # [v2.0 수정] 빈 사이클 타임 전달
            self.notifier.check_and_notify(m.name, "OFFLINE", "00:00:00", False, self.app.notify_enabled.get())

    def update_loop(self):
        for m in self.machines:
            w = self.app.widgets.get(m.ip)
            if not w: continue

            if m.is_connected:
                try: m.fetch_data()
                except OSError: m.drop_connection()
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
                # [v2.2 추가] 절전 복귀 등으로 끊긴 경우 자동 재연결
                if m.want_connected:
                    self.try_reconnect(m)

                if not self.app.is_hidden:
                    for k in ["mode", "status", "tool", "c_status"]:
                        w[k].configure(text="-", text_color="#444444")
                    w["time"].configure(text="-", text_color=("#FFFFFF", "#FFFFFF"))
                    w["c_time"].configure(text="-", text_color=("#FFFFFF", "#FFFFFF"))
                    w["btn"].configure(text="연결하기", fg_color=["#3B8ED0", "#1F6AA5"])

        self.app.after(3000 if self.app.is_hidden else 500, self.update_loop)

    def try_reconnect(self, m):
        """UI를 멈추지 않도록 백그라운드 스레드에서 재연결 시도 (10초 간격 제한)"""
        if getattr(m, "_reconnecting", False):
            return
        now = time.monotonic()
        if now - getattr(m, "_last_reconnect_try", 0.0) < 10:
            return
        m._last_reconnect_try = now
        m._reconnecting = True

        def _work():
            try:
                if m.connect():
                    logger.info(f"[{m.name}] 자동 재연결 성공")
                else:
                    logger.warning(f"[{m.name}] 자동 재연결 실패 (10초 후 재시도)")
            finally:
                m._reconnecting = False

        threading.Thread(target=_work, daemon=True).start()

if __name__ == "__main__":
    if is_already_running():
        import tkinter as tk
        r = tk.Tk(); r.withdraw(); messagebox.showwarning("알림", "이미 실행 중입니다."); r.destroy(); sys.exit(0)
    MainController().app.mainloop()