from plyer import notification
import datetime

class StatusNotifier:
    def __init__(self):
        self.last_states = {}

    def check_and_notify(self, machine_name, current_status, is_alarm, enabled):
        if not enabled: return None

        # 이전 상태 가져오기
        prev = self.last_states.get(machine_name, {"status": "OFFLINE", "alarm": False})
        
        now = datetime.datetime.now().strftime("%H:%M:%S")
        popup_trigger = None

        # 1. 🚨 기계 알람 (최우선순위)
        if is_alarm and not prev["alarm"]:
            title = f"🚨 [긴급 알람] {machine_name}"
            msg = f"발생 시간: {now}\n즉시 장비 상태를 확인하십시오!"
            self.send_toast(title, msg)
            popup_trigger = "ALARM_POPUP"

        # 2. ✅ 가공 완료 (RUN -> STOP/IDLE)
        elif "RUN" not in current_status and "RUN" in prev["status"]:
            title = f"✅ [가공 완료] {machine_name}"
            msg = f"완료 시간: {now}\n다음 가공 준비가 가능합니다."
            self.send_toast(title, msg)

        # 3. ⏸️ M코드 정지 (RUN -> HOLD)
        elif "HOLD" in current_status and "RUN" in prev["status"]:
            title = f"⏸️ [작업 정지] {machine_name}"
            msg = f"정지 시간: {now}\nM00/M01 코드가 감지되었습니다."
            self.send_toast(title, msg)

        # 상태 업데이트
        self.last_states[machine_name] = {"status": current_status, "alarm": is_alarm}
        return popup_trigger

    def send_toast(self, title, message):
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="CNC Watcher",
                app_icon=None,
                timeout=30  # 알람 유지 시간을 30초로 상향 조정
            )
        except Exception as e:
            print(f"알림 전송 실패: {e}")