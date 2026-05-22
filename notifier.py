from plyer import notification
import datetime
import threading
import os
import csv

class StatusNotifier:
    def __init__(self, icon_path=None, base_dir="."):
        self.icon_path = icon_path 
        self.last_states = {}      
        
        # [v2.0 추가] 로그 폴더 설정
        self.log_dir = os.path.join(base_dir, "logs")
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def log_to_csv(self, machine_name, start_time, end_time, cycle_time):
        """가공 이력을 일자별 CSV 파일로 저장합니다."""
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(self.log_dir, f"history_{today}.csv")
        file_exists = os.path.isfile(log_file)
        
        def _write():
            try:
                # utf-8-sig를 사용하여 엑셀에서 한글이 깨지지 않게 방지
                with open(log_file, mode='a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(["가공 일자", "장비명", "시작 시간", "종료 시간", "사이클 타임"])
                    writer.writerow([today, machine_name, start_time, end_time, cycle_time])
            except Exception as e:
                print(f"❌ 로그 저장 실패: {e}")
                
        # 파일 쓰기 딜레이 방지를 위해 스레드로 던짐
        threading.Thread(target=_write, daemon=True).start()

    def check_and_notify(self, machine_name, current_status, cycle_time, is_alarm, enabled):
        # 이전 상태 가져오기 (시작 시간 트래킹 추가)
        prev = self.last_states.get(machine_name, {"status": "OFFLINE", "alarm": False, "start_time": None})
        now_time = datetime.datetime.now().strftime("%H:%M:%S")
        popup_trigger = None
        
        # [v2.0 추가] 가공 시작(RUN) 시간 기록
        start_time = prev.get("start_time")
        if "RUN" in current_status and "RUN" not in prev["status"]:
            start_time = now_time

        if not enabled: 
            self.last_states[machine_name] = {"status": current_status, "alarm": is_alarm, "start_time": start_time}
            return None

        # 1. 🚨 기계 알람
        if is_alarm and not prev["alarm"]:
            title = f"🚨 [긴급 알람] {machine_name}"
            msg = f"발생 시간: {now_time}\n즉시 장비 상태를 확인하십시오!"
            self.send_toast(title, msg)
            popup_trigger = "ALARM_POPUP"

        # 2. ✅ 가공 완료 (RUN -> STOP/IDLE)
        elif "RUN" not in current_status and "RUN" in prev["status"]:
            title = f"✅ [가공 완료] {machine_name}"
            msg = f"완료 시간: {now_time}\n다음 가공 준비가 가능합니다."
            self.send_toast(title, msg)
            
            # [v2.0 추가] 가공이 끝나면 CSV에 데이터 기록
            actual_start = start_time if start_time else "-"
            self.log_to_csv(machine_name, actual_start, now_time, cycle_time)
            start_time = None # 기록 후 시작 시간 초기화

        # 3. ⏸️ M코드 정지 (RUN -> HOLD)
        elif "HOLD" in current_status and "RUN" in prev["status"]:
            title = f"⏸️ [작업 정지] {machine_name}"
            msg = f"정지 시간: {now_time}\nM00/M01 코드가 감지되었습니다."
            self.send_toast(title, msg)

        # 상태 업데이트
        self.last_states[machine_name] = {"status": current_status, "alarm": is_alarm, "start_time": start_time}
        return popup_trigger

    def send_toast(self, title, message):
        final_icon_path = self.icon_path if self.icon_path and os.path.exists(self.icon_path) else None

        def _notify():
            try:
                notification.notify(
                    title=title, message=message, app_name="Watcher v2.0",
                    app_icon=final_icon_path, timeout=30
                )
            except Exception as e:
                pass
        threading.Thread(target=_notify, daemon=True).start()