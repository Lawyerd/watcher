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

# [v3.0] 정지 시간·프로그램·결과 열 추가 (예전 5열 행도 그대로 읽힌다)
HISTORY_HEADER = ["가공 일자", "장비명", "시작 시간", "종료 시간", "사이클 타임", "정지 시간", "프로그램", "결과"]
ALARM_HEADER   = ["일자", "시간", "장비명", "구분", "알람 번호", "내용"]

RESET_STATUS = "STOP"   # fanuc_logic run_map의 0번(리셋) — M30으로 프로그램이 끝나거나 리셋 버튼을 누른 상태
PAUSE_TOAST_SEC = 30    # 프로그램 중간 멈춤이 이만큼 이어지면 토스트 한 번 (싱글 블록마다 뜨지 않게)


def hms_sec(t):
    """'HH:MM:SS' → 초"""
    try:
        h, m, s = (int(x) for x in str(t).split(":"))
    except ValueError:
        return 0
    return h * 3600 + m * 60 + s


def sec_hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def dur_text(sec):
    """알림 문구용 '6분 46초' / '1시간 5분'"""
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}시간 {m}분" if h else (f"{m}분 {s}초" if m else f"{s}초")


class StatusNotifier:
    def __init__(self, icon_path=None, base_dir=".", push=None):
        self.icon_path = icon_path
        self.push = push           # [v3.0] 휴대폰 푸시 (webpush.PushSender, 📡 켜져 있을 때만 실제로 보냄)
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

    def log_to_csv(self, machine_name, row, when):
        """가공 이력 한 줄을 끝난 날짜의 CSV에 저장. row = [시작, 종료, 사이클, 정지, 프로그램, 결과]"""
        day = when.strftime("%Y-%m-%d")
        if day == datetime.datetime.now().strftime("%Y-%m-%d") and row[-1] != "알람":
            counts = self.today_counts()
            counts[machine_name] = counts.get(machine_name, 0) + 1
        self._append_csv(f"history_{day}.csv", HISTORY_HEADER, [[day, machine_name] + row])

    def today_counts(self):
        """[v2.4] 오늘 가공 완료 횟수 {장비명: n}. 앱을 재시작해도 오늘 CSV에서 다시 센다 (알람으로 끝난 가공은 제외)."""
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        if self._count_date != today:
            self._count_date, self._counts = today, {}
            try:
                with open(os.path.join(self.log_dir, f"history_{today}.csv"), newline='', encoding='utf-8-sig') as f:
                    for row in list(csv.reader(f))[1:]:
                        if len(row) >= 2 and (len(row) < 8 or row[7] != "알람"):
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

    def check_and_notify(self, machine_name, current_status, cycle_time, is_alarm, enabled, alarms=(), program=None):
        """장비 스레드가 0.5초마다 호출. 알람 알림, 가공 기록(프로그램 한 번 = 한 줄), 정지 알림을 처리한다.
        enabled(🔔)는 PC 토스트만 끈다 — CSV 기록과 휴대폰 푸시는 그대로."""
        prev = self.last_states.get(machine_name, {"status": "OFFLINE", "alarm": False, "job": None})
        now = datetime.datetime.now()
        now_time = now.strftime("%H:%M:%S")
        popup_trigger = None
        job = prev["job"]

        # [v2.2] 연결 해제/끊김(OFFLINE)은 가공 이벤트로 취급하지 않음 (진행 중 가공도 끝내지 않고 이어 받음)
        is_offline = "OFFLINE" in current_status

        # [v2.4] 알람 발생/해제 이력 (끊김은 알람 해제로 취급하지 않음)
        if not is_offline:
            self.log_alarm_changes(machine_name, alarms)

        # 1. 🚨 기계 알람
        if is_alarm and not prev["alarm"]:
            detail = "\n".join(f"{a['code']} {a['msg']}" for a in alarms[:2])
            if enabled:
                msg = f"{detail}\n발생 시간: {now_time}" if alarms else f"발생 시간: {now_time}\n즉시 장비 상태를 확인하십시오!"
                self.send_toast(f"🚨 [긴급 알람] {machine_name}", msg)
                popup_trigger = "ALARM_POPUP"
            if self.push:
                self.push.send("alarm", f"🚨 {machine_name} 알람", detail or "장비 상태를 확인하세요", tag=f"alarm-{machine_name}")

        # 2. 가공 기록 — [v3.0] 프로그램 한 번(리셋될 때까지)을 한 줄로. 중간 멈춤(M00·M01·싱글 블록·피드 홀드)은
        #    묶는다. 예전엔 RUN에서 벗어날 때마다 '가공 완료'로 기록해 한 프로그램이 여러 줄로 쪼개졌고,
        #    장비 사이클 타임은 멈춰도 계속 누적되므로 줄마다 시작→끝과 사이클 타임이 맞지 않았다.
        if not is_offline:
            running, was_running = "RUN" in current_status, "RUN" in prev["status"]
            cyc = hms_sec(cycle_time)
            if running:
                if job and not was_running and cyc + 2 < job["cyc"]:
                    self._finish_job(machine_name, job, enabled)   # 사이클 카운터가 0부터 다시 → 이전 프로그램은 끝난 것
                    job = None
                if job is None:
                    job = {"start": now, "alarm": False, "program": None}
                job.update(cyc=cyc, end=now, paused_at=None, pause_toast=False, program=program or job["program"])
            if job and is_alarm:
                job["alarm"] = True
            if job and not running:
                if was_running:   # 멈춘 순간의 시각·사이클 타임이 이 가공의 끝 (리셋은 한참 뒤에 누를 수도 있음)
                    job.update(cyc=max(cyc, job["cyc"]), end=now, paused_at=now)
                if current_status == RESET_STATUS:
                    self._finish_job(machine_name, job, enabled)
                    job = None
                elif (enabled and job["paused_at"] and not job["pause_toast"]
                      and (now - job["paused_at"]).total_seconds() >= PAUSE_TOAST_SEC):
                    job["pause_toast"] = True
                    self.send_toast(f"⏸️ [작업 정지] {machine_name}",
                                    f"정지 시간: {job['paused_at'].strftime('%H:%M:%S')}\n가공 중간에 {PAUSE_TOAST_SEC}초 넘게 멈춰 있습니다.")

        self.last_states[machine_name] = {"status": current_status, "alarm": is_alarm, "job": job}
        return popup_trigger

    def _finish_job(self, machine_name, job, enabled):
        """가공 한 번을 CSV에 기록하고, 정상으로 끝났으면 가공 완료 알림 (알람으로 끝난 가공은 기록만)"""
        cyc = job["cyc"]
        pause = max(0, int((job["end"] - job["start"]).total_seconds()) - cyc)   # 시작→끝 중 가공하지 않은 시간
        result = "알람" if job["alarm"] else "완료"
        self.log_to_csv(machine_name, [job["start"].strftime("%H:%M:%S"), job["end"].strftime("%H:%M:%S"),
                                       sec_hms(cyc), sec_hms(pause), job["program"] or "", result], job["end"])
        if result != "완료":
            return
        done = self.today_counts().get(machine_name, 0)
        if enabled:
            self.send_toast(f"✅ [가공 완료] {machine_name}",
                            f"가공 {dur_text(cyc)} · 완료 {job['end'].strftime('%H:%M:%S')}\n다음 가공 준비가 가능합니다.")
        if self.push:
            body = " · ".join(x for x in (f"가공 {dur_text(cyc)}", job["program"], f"오늘 {done}회째") if x)
            self.push.send("done", f"✅ {machine_name} 가공 완료", body, tag=f"done-{machine_name}")

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