import os
import sys
import json
import time
import io
import ctypes
import datetime
import socket
import logging
import threading
from tkinter import messagebox
from PIL import Image, ImageDraw
import pystray
from fanuc_logic import FanucMachine
from monitor_ui import AppUI, SettingsDialog, state_of, summary_of
from notifier import StatusNotifier
from remote_server import RemoteServer, local_urls

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
FONTS_DIR    = os.path.join(BASE_DIR, "fonts")

def load_private_fonts():
    """[v2.3] fonts/ 폴더의 폰트를 이 프로세스 전용으로 로드.
    시스템 설치 없이 앱 안에서만 사용 가능 (JetBrains Mono 동봉 배포용)."""
    if not os.path.isdir(FONTS_DIR): return
    FR_PRIVATE = 0x10
    for f in os.listdir(FONTS_DIR):
        if f.lower().endswith((".ttf", ".otf")):
            try:
                ctypes.windll.gdi32.AddFontResourceExW(os.path.join(FONTS_DIR, f), FR_PRIVATE, None)
            except Exception as e:
                logger.error(f"폰트 로드 실패 ({f}): {e}")

if os.path.exists(DLL_DIR):
    if hasattr(os, 'add_dll_directory'): os.add_dll_directory(DLL_DIR)
    os.environ['PATH'] = DLL_DIR + os.pathsep + os.environ['PATH']

def draw_watcher_icon(px=512):
    """[v2.3] 펄스 라인 아이콘: 다크 라운드 사각형 + 초록 심박 라인 (512px 렌더 후 축소)"""
    img = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = px / 64
    d.rounded_rectangle((2 * s, 2 * s, 62 * s, 62 * s), radius=14 * s, fill="#1C1C21")
    pts = [(8, 32), (20, 32), (26, 16), (34, 48), (40, 32), (56, 32)]
    pts = [(x * s, y * s) for x, y in pts]
    w = int(5 * s)
    d.line(pts, fill="#30D158", width=w, joint="curve")
    r = w / 2  # 라인 양 끝을 둥글게
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill="#30D158")
    return img

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
            try:
                self.app.iconbitmap(ICON_PATH)
                self.app.icon_path = ICON_PATH   # 설정 창/알람 팝업 등 자식 창에서도 사용
            except Exception as e: logger.error(f"아이콘 적용 실패: {e}")

        self._bind_conn_buttons()
        self.app.settings_btn.configure(command=self.open_settings)

        # [v2.4] 원격 모니터링 (휴대폰 등에서 상태 확인용 읽기 전용 서버)
        self.remote = RemoteServer(log_dir=self.notifier.log_dir, icons=self._web_icons())
        self.app.remote_btn.configure(command=self.toggle_remote)

        self.setup_tray()
        self.update_loop()

    def _web_icons(self):
        """휴대폰 홈 화면 아이콘용 PNG (192/512px)"""
        icons = {}
        img = draw_watcher_icon()
        for px in (192, 512):
            buf = io.BytesIO()
            img.resize((px, px), Image.LANCZOS).save(buf, format="PNG")
            icons[px] = buf.getvalue()
        return icons

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
                draw_watcher_icon().save(ICON_PATH, format='ICO',
                                         sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
            except Exception as e: logger.error(f"아이콘 생성 실패: {e}")
        # 토스트용 고해상도 PNG (256px)
        if not os.path.exists(ICON_PNG):
            try:
                os.makedirs(ICONS_DIR, exist_ok=True)
                draw_watcher_icon().resize((256, 256), Image.LANCZOS).save(ICON_PNG, format='PNG')
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
        self.remote.stop()
        self.tray_icon.stop()
        for m in self.machines: m.disconnect()
        self.app.quit()

    def toggle_remote(self):
        if self.remote.running:
            self.remote.stop()
            self.app.set_remote_state(False)
            return
        try:
            self.remote.start()
        except OSError as e:
            logger.error(f"원격 모니터링 시작 실패: {e}")
            messagebox.showerror("원격 모니터링", f"서버를 시작할 수 없습니다 (포트 {self.remote.port}).\n{e}")
            return
        self.publish_snapshot()
        self.app.set_remote_state(True, local_urls(self.remote.port))

    def _track_state(self, m):
        """[v2.4] 상태(RUN/ALARM/…)가 바뀐 시각 기록 → 휴대폰 페이지의 'N분째' 표시용"""
        st = state_of(m.data["status"], m.data["is_alarm"], m.is_connected)
        if getattr(m, "_state", None) != st:
            m._state, m._state_since = st, datetime.datetime.now()

    def publish_snapshot(self):
        """원격 서버로 넘길 상태 스냅샷 (메인 스레드에서 생성 → 서버 스레드는 FOCAS 접근 안 함)"""
        now = datetime.datetime.now()
        counts = self.notifier.today_counts()
        machines = []
        for m in self.machines:
            d = m.data
            since = getattr(m, "_state_since", now)
            machines.append({
                "name": m.name, "connected": m.is_connected,
                "state": state_of(d["status"], d["is_alarm"], m.is_connected),
                "status": d["status"], "mode": d["mode"], "tool": d["tool"],
                "next_tool": d["next_tool"], "cycle_time": d["cycle_time"],
                "alarms": d["alarms"],
                "state_since": since.strftime("%H:%M:%S"),
                "state_sec": int((now - since).total_seconds()),
                "done_today": counts.get(m.name, 0),
            })
        col, txt, _ = summary_of(self.machines)
        self.remote.update_snapshot({
            "updated": now.strftime("%H:%M:%S"),
            "summary": {"color": col, "text": txt, "total": len(self.machines)},
            "machines": machines,
        })

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
            if m.is_connected:
                try: m.fetch_data()
                except OSError: m.drop_connection()
                except Exception as e: logger.error(f"fetch_data 예외: {e}", exc_info=True)

                if m.is_connected:
                    st  = m.data["status"]
                    cyc = m.data["cycle_time"]

                    alarms = m.data["alarms"]

                    notif_res = self.notifier.check_and_notify(
                        m.name, st, cyc, m.data["is_alarm"], self.app.notify_enabled.get(), alarms
                    )

                    if notif_res == "ALARM_POPUP": self.app.show_emergency_popup(m.name, alarms)

                    if not self.app.is_hidden:
                        # [v2.3] 상태 반영은 AppUI.apply_status가 일괄 처리
                        self.app.apply_status(m.ip, m.data["mode"], st, m.data["tool"],
                                              cyc, m.data["is_alarm"], True, alarms)
            else:
                # [v2.2 추가] 절전 복귀 등으로 끊긴 경우 자동 재연결
                if m.want_connected:
                    self.try_reconnect(m)

                if not self.app.is_hidden:
                    self.app.apply_status(m.ip, "-", "OFFLINE", "-", "-", False, False)

            self._track_state(m)

        if not self.app.is_hidden:
            self.app.update_summary()

        if self.remote.running:
            self.publish_snapshot()

        self.app.after(3000 if self.app.is_hidden else 500, self.update_loop)

    def try_reconnect(self, m):
        """자동 재연결 (10초 간격 제한).
        FOCAS 핸들은 그 핸들을 만든 스레드에서만 유효하므로(다른 스레드에서 쓰면 EW_HANDLE -8),
        백그라운드 스레드는 TCP 도달성 확인만 하고 실제 연결은 메인 스레드에서 수행한다."""
        if getattr(m, "_reconnecting", False):
            return
        now = time.monotonic()
        if now - getattr(m, "_last_reconnect_try", 0.0) < 10:
            return
        m._last_reconnect_try = now
        m._reconnecting = True

        def _probe():
            try:
                s = socket.create_connection((m.ip, m.port), timeout=2)
                s.close()
            except OSError:
                m._reconnecting = False
                logger.warning(f"[{m.name}] 재연결 대기: 장비 응답 없음 (10초 후 재시도)")
                return
            # 도달 가능 확인됨 → 실제 FOCAS 연결은 메인 스레드에서
            self.app.after(0, lambda: self._finish_reconnect(m))

        threading.Thread(target=_probe, daemon=True).start()

    def _finish_reconnect(self, m):
        try:
            if not m.is_connected and m.want_connected:
                if m.connect():
                    logger.info(f"[{m.name}] 자동 재연결 성공")
                else:
                    logger.warning(f"[{m.name}] 자동 재연결 실패 (10초 후 재시도)")
        finally:
            m._reconnecting = False

if __name__ == "__main__":
    if is_already_running():
        import tkinter as tk
        r = tk.Tk(); r.withdraw(); messagebox.showwarning("알림", "이미 실행 중입니다."); r.destroy(); sys.exit(0)
    load_private_fonts()   # AppUI의 폰트 탐색보다 먼저 로드해야 함
    MainController().app.mainloop()