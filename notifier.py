import datetime
import threading
import logging
import os
import csv

logger = logging.getLogger(__name__)

# [v2.2 수정] Windows 10/11 네이티브 토스트(winotify) 우선 사용
#             plyer의 구식 풍선 알림은 Win11에서 오류 없이 무시되는 경우가 많음
try:
    from winotify import Notification, audio
    HAS_WINOTIFY = True
except ImportError:
    from plyer import notification
    HAS_WINOTIFY = False
    logger.warning("winotify 미설치 → plyer 알림으로 대체 (Win11에서 표시 안 될 수 있음)")

HISTORY_HEADER = ["가공 일자", "장비명", "시작 시간", "종료 시간", "사이클 타임"]
ALARM_HEADER   = ["일자", "시간", "장비명", "구분", "알람 번호", "내용"]

class StatusNotifier:
    def __init__(self, icon_path=None, base_dir="."):
        self.icon_path = icon_path
        self.last_states = {}
        self.active_alarms = {}    # [v2.4] 장비별 현재 알람 {code: alarm} — 발생/해제 이력 비교용
        self._csv_lock = threading.Lock()
        self._count_date = None    # [v2.4] 오늘 가공 완료 횟수 캐시 (날짜가 바뀌면 CSV에서 다시 셈)
        self._counts = {}

        # [v2.0 추가] 로그 폴더 설정
        self.log_dir = os.path.join(base_dir, "logs")
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def _append_csv(self, filename, header, rows):
        log_file = os.path.join(self.log_dir, filename)

        def _write():
            try:
                # 두 장비가 동시에 기록해도 헤더가 중복되지 않게 잠금 안에서 존재 여부 확인
                with self._csv_lock:
                    file_exists = os.path.isfile(log_file)
                    # utf-8-sig를 사용하여 엑셀에서 한글이 깨지지 않게 방지
                    with open(log_file, mode='a', newline='', encoding='utf-8-sig') as f:
                        writer = csv.writer(f)
                        if not file_exists:
                            writer.writerow(header)
                        writer.writerows(rows)
            except Exception as e:
                logger.error(f"로그 저장 실패 ({filename}): {e}")

        # 파일 쓰기 딜레이 방지를 위해 스레드로 던짐
        threading.Thread(target=_write, daemon=True).start()

    def log_to_csv(self, machine_name, start_time, end_time, cycle_time):
        """가공 이력을 일자별 CSV 파일로 저장합니다."""
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        counts = self.today_counts()
        counts[machine_name] = counts.get(machine_name, 0) + 1
        self._append_csv(f"history_{today}.csv", HISTORY_HEADER,
                         [[today, machine_name, start_time, end_time, cycle_time]])

    def today_counts(self):
        """[v2.4] 오늘 가공 완료 횟수 {장비명: n}. 앱을 재시작해도 오늘 CSV에서 다시 센다."""
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        if self._count_date != today:
            self._count_date, self._counts = today, {}
            try:
                with open(os.path.join(self.log_dir, f"history_{today}.csv"), newline='', encoding='utf-8-sig') as f:
                    for row in list(csv.reader(f))[1:]:
                        if len(row) >= 2:
                            self._counts[row[1]] = self._counts.get(row[1], 0) + 1
            except OSError:
                pass
        return self._counts

    def log_alarm_changes(self, machine_name, alarms):
        """[v2.4] 알람 발생/해제를 logs/alarm_YYYY-MM-DD.csv에 기록 (알림 ON/OFF와 무관)"""
        now = datetime.datetime.now()
        today, now_time = now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")
        prev = self.active_alarms.get(machine_name, {})
        cur = {a["code"]: a for a in alarms}

        rows = [[today, a["since"], machine_name, "발생", code, a["msg"]]
                for code, a in cur.items() if code not in prev]
        rows += [[today, now_time, machine_name, "해제", code, a["msg"]]
                 for code, a in prev.items() if code not in cur]
        self.active_alarms[machine_name] = cur
        if rows:
            self._append_csv(f"alarm_{today}.csv", ALARM_HEADER, rows)

    def check_and_notify(self, machine_name, current_status, cycle_time, is_alarm, enabled, alarms=()):
        # 이전 상태 가져오기 (시작 시간 트래킹 추가)
        prev = self.last_states.get(machine_name, {"status": "OFFLINE", "alarm": False, "start_time": None})
        now_time = datetime.datetime.now().strftime("%H:%M:%S")
        popup_trigger = None

        # [v2.0 추가] 가공 시작(RUN) 시간 기록
        start_time = prev.get("start_time")
        if "RUN" in current_status and "RUN" not in prev["status"]:
            start_time = now_time

        # [v2.2 수정] 연결 해제/끊김(OFFLINE)은 가공 이벤트로 취급하지 않음
        #             (수동 해제 시 가짜 '가공 완료' 기록 방지)
        is_offline = "OFFLINE" in current_status

        # [v2.4] 알람 발생/해제 이력 (끊김은 알람 해제로 취급하지 않음)
        if not is_offline:
            self.log_alarm_changes(machine_name, alarms)

        # 1. 🚨 기계 알람
        if is_alarm and not prev["alarm"]:
            if enabled:
                title = f"🚨 [긴급 알람] {machine_name}"
                if alarms:
                    detail = "\n".join(f"{a['code']} {a['msg']}" for a in alarms[:2])
                    msg = f"{detail}\n발생 시간: {now_time}"
                else:
                    msg = f"발생 시간: {now_time}\n즉시 장비 상태를 확인하십시오!"
                self.send_toast(title, msg)
                popup_trigger = "ALARM_POPUP"

        # 2. ✅ 가공 완료 (RUN -> STOP/IDLE)
        elif not is_offline and "RUN" not in current_status and "RUN" in prev["status"]:
            if enabled:
                title = f"✅ [가공 완료] {machine_name}"
                msg = f"완료 시간: {now_time}\n다음 가공 준비가 가능합니다."
                self.send_toast(title, msg)

            # [v2.2 수정] CSV 이력은 알림 ON/OFF와 무관하게 항상 기록
            actual_start = start_time if start_time else "-"
            self.log_to_csv(machine_name, actual_start, now_time, cycle_time)
            start_time = None # 기록 후 시작 시간 초기화

        # 3. ⏸️ M코드 정지 (RUN -> HOLD)
        elif "HOLD" in current_status and "RUN" in prev["status"]:
            if enabled:
                title = f"⏸️ [작업 정지] {machine_name}"
                msg = f"정지 시간: {now_time}\nM00/M01 코드가 감지되었습니다."
                self.send_toast(title, msg)

        # 상태 업데이트
        self.last_states[machine_name] = {"status": current_status, "alarm": is_alarm, "start_time": start_time}
        return popup_trigger

    def send_toast(self, title, message):
        final_icon_path = self.icon_path if self.icon_path and os.path.exists(self.icon_path) else ""

        def _notify():
            try:
                if HAS_WINOTIFY:
                    toast = Notification(
                        app_id="CNC Watcher", title=title, msg=message,
                        icon=final_icon_path, duration="long"
                    )
                    toast.set_audio(audio.Default, loop=False)
                    toast.show()
                else:
                    notification.notify(
                        title=title, message=message, app_name="CNC Watcher",
                        app_icon=final_icon_path or None, timeout=30
                    )
            except Exception as e:
                logger.error(f"토스트 알림 실패: {e}")
        threading.Thread(target=_notify, daemon=True).start()