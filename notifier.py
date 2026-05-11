from plyer import notification

class StatusNotifier:
    def __init__(self):
        self.app_name = "CNC Watcher"
        # 각 기계별 이전 상태를 저장하기 위한 딕셔너리
        self.last_statuses = {} 
        self.last_alarms = {}

    def check_and_notify(self, machine_name, current_status, is_alarm, enabled):
        if not enabled:
            return

        # 1. 초기 상태 설정 (딕셔너리에 기계가 없으면 추가)
        if machine_name not in self.last_statuses:
            self.last_statuses[machine_name] = current_status
            self.last_alarms[machine_name] = is_alarm
            return

        old_status = self.last_statuses[machine_name]
        old_alarm = self.last_alarms[machine_name]

        # 2. 알람 상태 변화 감지 (정상 -> 알람)
        if is_alarm and not old_alarm:
            self.send(f"⚠️ {machine_name} 알람 발생", "기계에 알람이 발생했습니다. 즉시 확인하세요!")

        # 3. 운전 상태 변화 감지
        if old_status != current_status:
            if current_status == "RUN":
                self.send(f"▶️ {machine_name} 가공 시작", "프로그램 운전을 시작했습니다.")
            elif current_status == "HOLD(M00)":
                self.send(f"⏸️ {machine_name} 일시 정지", "M00 또는 피드 홀드로 가공이 멈췄습니다.")
            elif current_status == "STOP" and old_status == "RUN":
                self.send(f"✅ {machine_name} 가공 완료", "모든 공정이 끝나고 장비가 정지했습니다.")
            elif current_status == "OFFLINE":
                self.send(f"🔌 {machine_name} 연결 끊김", "PC와 기계의 통신이 중단되었습니다.")

        # 4. 현재 상태를 이전 상태로 저장
        self.last_statuses[machine_name] = current_status
        self.last_alarms[machine_name] = is_alarm

    def send(self, title, message):
        try:
            notification.notify(
                title=title,
                message=message,
                app_name=self.app_name,
                timeout=5
            )
        except Exception as e:
            print(f"알림 전송 실패: {e}")