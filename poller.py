import time
import json
import queue
import logging
import datetime
import threading
from fanuc_logic import FanucMachine
from remote_server import tailscale_installed

logger = logging.getLogger(__name__)

POLL_SEC = 0.5      # 장비 읽기 주기 (전용 스레드라 화면을 막지 않으므로 숨김 상태에서도 그대로)
RETRY_SEC = 10      # 끊긴 장비 자동 재연결 간격


def state_of(status, is_alarm, connected):
    if not connected or "OFFLINE" in status: return "OFFLINE"
    if is_alarm:            return "ALARM"
    if "RUN" in status:     return "RUN"
    if "HOLD" in status:    return "HOLD"
    return "IDLE"


def summary_of(machines):
    """PC 화면 헤더 가동 요약 (점 색으로 쓸 상태, 문구). 색 값은 화면 쪽(web/common.css)에서 정한다."""
    connected = [m for m in machines if m.is_connected]
    alarm = sum(1 for m in connected if m.data.get("is_alarm"))
    running = sum(1 for m in connected if "RUN" in m.data.get("status", ""))
    if alarm:          return "ALARM", f"알람 {alarm}대 발생"
    if not connected:  return "OFFLINE", "연결된 장비 없음"
    if running:        return "RUN", f"{running}대 가동 중"
    return "IDLE", f"{len(connected)}대 대기 중"


class Poller(threading.Thread):
    """[v3.0] FOCAS 전용 스레드 — 연결·읽기·자동 재연결·해제를 모두 이 스레드에서 한다.
    FOCAS 핸들은 만든 스레드에서만 유효하므로 한 스레드가 전부 맡으면 제약이 자연히 지켜지고,
    연결이 3초 걸려도 화면은 멈추지 않는다.

    화면(js_api 스레드)은 request()로 명령을 넣고 snapshot()/pop_events()로 결과만 읽는다.
    원격 서버 켜기/끄기도 여기서 한다 — 절전 차단(SetThreadExecutionState)은 호출한 스레드가
    살아 있는 동안만 유지되는데, js_api 호출 스레드는 바로 끝나기 때문."""

    def __init__(self, configs, dll_path, notifier, util, remote, state_path=None):
        super().__init__(name="focas-poller", daemon=True)
        self.dll_path = dll_path
        self.notifier, self.util, self.remote = notifier, util, remote
        self.machines = [self._make(c) for c in configs]
        # 상태 기억: 지난번 꺼질 때 연결돼 있던 장비는 자동 재연결 대상으로 두고 시작
        # (바로 connect하지 않는 이유 — 부팅 직후 장비가 아직 꺼져 있어도 10초마다 다시 붙도록)
        self.state_path = state_path
        self._saved = self._load_state()
        for m in self.machines:
            m.want_connected = self._key(m) in self._saved
        self.notify_enabled = True
        self.cmds = queue.Queue()
        self._lock = threading.Lock()
        self._snap = {"machines": [], "summary": {"state": "OFFLINE", "text": "불러오는 중…", "total": 0}, "remote": False}
        self._events = []

    def _make(self, c):
        return FanucMachine(c["name"], c["ip"], port=c.get("port", 8193), dll_path=self.dll_path)

    @staticmethod
    def _key(m):
        return f"{m.ip}:{m.port}"

    def _load_state(self):
        if not self.state_path:
            return []
        try:
            with open(self.state_path, encoding="utf-8") as f:
                return sorted(json.load(f).get("connected", []))
        except (OSError, ValueError, AttributeError, TypeError):
            return []

    def _save_state(self):
        """연결을 원하는 장비 목록이 바뀌었을 때만 저장 (연결·해제·설정 변경 모두 여기서 잡힘)"""
        want = sorted(self._key(m) for m in self.machines if m.want_connected)
        if want == self._saved or not self.state_path:
            return
        self._saved = want
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump({"connected": want}, f, indent=4)
        except OSError as e:
            logger.error(f"연결 상태 저장 실패: {e}")

    # ── 화면 쪽에서 부르는 것 (스레드 안전) ──────────────────
    def request(self, action, arg=None):
        self.cmds.put((action, arg))

    def snapshot(self):
        with self._lock:
            return self._snap

    def busy_names(self):
        """[v3.1] 프로그램이 아직 끝나지 않은(리셋 전) 연결된 장비 — '가공 끝나면 업데이트'가 기다린다.
        가공 중에 앱이 꺼지면 그 가공 한 줄의 시작 시각이 다시 켠 시각으로 틀어지기 때문."""
        states = self.notifier.last_states
        return [m["name"] for m in self.snapshot()["machines"]
                if m["connected"] and (states.get(m["name"]) or {}).get("job")]

    def pop_events(self):
        with self._lock:
            events, self._events = self._events, []
        return events

    def _event(self, **e):
        with self._lock:
            self._events.append(e)

    # ── 이 스레드 안에서만 ──────────────────────────────────
    def _find(self, ip):
        return next((m for m in self.machines if m.ip == ip), None)

    def _disconnect(self, m):
        m.want_connected = False
        if m.is_connected:
            m.disconnect()
        self.notifier.check_and_notify(m.name, "OFFLINE", "00:00:00", False, self.notify_enabled)

    def _set_machines(self, configs):
        """설정 창에서 저장: IP/포트가 같은 장비는 기존 객체를 재사용해 연결 유지, 빠진 장비는 해제"""
        old = {(m.ip, m.port): m for m in self.machines}
        new = []
        for c in configs:
            m = old.pop((c["ip"], c.get("port", 8193)), None) or self._make(c)
            m.name = c["name"]
            new.append(m)
        for m in old.values():
            self._disconnect(m)
        self.machines = new
        logger.info(f"장비 설정 변경 적용: {[m.name for m in new]}")

    def _handle_commands(self):
        while True:
            try:
                action, arg = self.cmds.get_nowait()
            except queue.Empty:
                return False
            try:
                if action == "connect":
                    m = self._find(arg)
                    if m and not m.is_connected:
                        if m.connect():
                            m.want_connected = True
                        else:
                            self._event(type="error", msg=f"[{m.name}] 연결 불가")
                elif action == "disconnect":
                    m = self._find(arg)
                    if m:
                        self._disconnect(m)
                elif action == "set_machines":
                    self._set_machines(arg)
                elif action == "remote_start":
                    if not tailscale_installed():   # 화면(Api)에서도 막지만, 서버를 켜는 유일한 곳이라 여기서 한 번 더
                        logger.warning("Tailscale 미설치 → 원격 모니터링 시작 거부")
                        self._event(type="error", msg="Tailscale이 설치되지 않은 PC라 원격 모니터링을 켤 수 없습니다.")
                        continue
                    try:
                        self.remote.start()
                    except OSError as e:
                        logger.error(f"원격 모니터링 시작 실패: {e}")
                        self._event(type="error", msg=f"원격 서버를 시작할 수 없습니다 (포트 {self.remote.port}).\n{e}")
                elif action == "remote_stop":
                    self.remote.stop()
                elif action == "shutdown":
                    self.remote.stop()
                    self.util.close([m.name for m in self.machines])
                    for m in self.machines:
                        if m.is_connected:
                            m.disconnect()   # 핸들 해제도 만든 스레드에서
                    return True
            except Exception as e:
                logger.error(f"명령 처리 실패 ({action}): {e}", exc_info=True)

    def _poll(self, m):
        if m.is_connected:
            try:
                m.fetch_data()
            except OSError:
                m.drop_connection()
            except Exception as e:
                logger.error(f"fetch_data 예외: {e}", exc_info=True)
            if m.is_connected:
                d = m.data
                res = self.notifier.check_and_notify(m.name, d["status"], d["cycle_time"], d["is_alarm"],
                                                     self.notify_enabled, d["alarms"], d["program"])
                if res == "ALARM_POPUP":
                    self._event(type="alarm", name=m.name, alarms=d["alarms"])
        elif m.want_connected and time.monotonic() - getattr(m, "_retry", 0) > RETRY_SEC:
            # 절전 복귀 등으로 끊긴 경우 자동 재연결 — 이 스레드라서 3초 걸려도 화면은 안 멈춤
            m._retry = time.monotonic()
            logger.info(f"[{m.name}] 자동 재연결 {'성공' if m.connect() else '실패 (10초 후 재시도)'}")

        st = state_of(m.data["status"], m.data["is_alarm"], m.is_connected)
        if getattr(m, "_state", None) != st:
            m._state, m._state_since = st, datetime.datetime.now()
        self.util.update(m.name, st)

    def _build_snapshot(self):
        now = datetime.datetime.now()
        counts = self.notifier.today_counts()
        machines = []
        for m in self.machines:
            d, since = m.data, getattr(m, "_state_since", now)
            machines.append({
                "name": m.name, "ip": m.ip, "port": m.port, "connected": m.is_connected,
                "state": state_of(d["status"], d["is_alarm"], m.is_connected),
                "status": d["status"], "mode": d["mode"], "tool": d["tool"], "next_tool": d["next_tool"],
                "program": d["program"], "cycle_time": d["cycle_time"], "alarms": d["alarms"],
                "spindle_load": d["spindle_load"], "spindle_rpm": d["spindle_rpm"], "axis_loads": d["axis_loads"],
                "state_since": since.strftime("%H:%M:%S"), "state_sec": int((now - since).total_seconds()),
                "done_today": counts.get(m.name, 0), "util": self.util.summary(m.name),
            })
        st, txt = summary_of(self.machines)
        return {"updated": now.strftime("%H:%M:%S"), "summary": {"state": st, "text": txt, "total": len(machines)},
                "machines": machines, "remote": self.remote.running, "notify": self.notify_enabled}

    def run(self):
        logger.info("장비 스레드 시작")
        while True:
            t = time.perf_counter()
            if self._handle_commands():
                logger.info("장비 스레드 종료")   # 종료 때 해제한 연결은 저장하지 않음 → 다음 실행 때 복원
                return
            self._save_state()
            for m in list(self.machines):
                self._poll(m)
            snap = self._build_snapshot()
            snap["loop_ms"] = round((time.perf_counter() - t) * 1000)
            with self._lock:
                self._snap = snap
            if self.remote.running:
                # 휴대폰(인터넷 공개 가능)에는 IP·포트를 빼고 넘긴다
                self.remote.update_snapshot(dict(snap, machines=[
                    {k: v for k, v in m.items() if k not in ("ip", "port")} for m in snap["machines"]]))
            time.sleep(max(0.05, POLL_SEC - (time.perf_counter() - t)))
