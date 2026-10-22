import os
import csv
import time
import logging
import datetime

logger = logging.getLogger(__name__)

HEADER = ["시간", "장비명", "상태"]
HEARTBEAT_SEC = 60


def _sec(dt):
    return dt.hour * 3600 + dt.minute * 60 + dt.second


def _hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


class UtilizationTracker:
    """[v2.4] 장비별 상태 변화(RUN/HOLD/IDLE/ALARM/OFFLINE)를 logs/state_YYYY-MM-DD.csv에 남기고
    오늘 0시부터의 가동률(RUN 시간 비율)과 타임라인 구간을 계산한다.

    앱이 꺼져 있던 시간은 알 수 없으므로, 1분마다 CSV 파일 수정 시각을 갱신(하트비트)해 두고
    다음 실행 때 그 시각 이후를 OFFLINE으로 처리한다 (비정상 종료 시 마지막 상태가 계속된 것으로 계산되는 것 방지)."""

    def __init__(self, log_dir):
        self.log_dir = log_dir
        self.date = None
        self.events = {}   # 장비명 → [(0시 기준 초, 상태), …] 시간순
        self._beat_at = 0.0
        self._load(datetime.datetime.now())

    def _path(self):
        return os.path.join(self.log_dir, f"state_{self.date}.csv")

    def _load(self, now):
        self.date, self.events = now.strftime("%Y-%m-%d"), {}
        try:
            with open(self._path(), newline="", encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))[1:]
            alive = _sec(datetime.datetime.fromtimestamp(os.path.getmtime(self._path())))
        except OSError:
            return
        for row in rows:
            if len(row) < 3:
                continue
            try:
                h, m, s = (int(x) for x in row[0].split(":"))
            except ValueError:
                continue
            self.events.setdefault(row[1], []).append((h * 3600 + m * 60 + s, row[2]))
        # 지난 실행이 끝난(마지막 하트비트) 시점부터는 상태를 알 수 없음 → OFFLINE
        for name, ev in self.events.items():
            if ev[-1][1] != "OFFLINE":
                self._append(name, "OFFLINE", max(alive, ev[-1][0]))

    def _append(self, name, state, sec):
        self.events.setdefault(name, []).append((sec, state))
        path, new = self._path(), not os.path.isfile(self._path())
        try:
            with open(path, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(HEADER)
                w.writerow([_hms(sec), name, state])
        except OSError as e:
            logger.error(f"상태 기록 실패: {e}")

    def update(self, name, state):
        """메인 루프에서 장비마다 호출. 상태가 바뀐 경우에만 기록한다."""
        now = datetime.datetime.now()
        if now.strftime("%Y-%m-%d") != self.date:
            # 자정: 어제 마지막 상태를 오늘 0시부터 이어서 시작
            last = {n: ev[-1][1] for n, ev in self.events.items() if ev}
            self.date, self.events = now.strftime("%Y-%m-%d"), {}
            for n, st in last.items():
                self._append(n, st, 0)
        ev = self.events.get(name)
        if not ev or ev[-1][1] != state:
            self._append(name, state, _sec(now))
        if time.monotonic() - self._beat_at > HEARTBEAT_SEC:
            self._beat_at = time.monotonic()
            try:
                os.utime(self._path())
            except OSError:
                pass

    def close(self, names):
        """정상 종료 시 OFFLINE으로 마감"""
        for name in names:
            ev = self.events.get(name)
            if ev and ev[-1][1] != "OFFLINE":
                self._append(name, "OFFLINE", _sec(datetime.datetime.now()))

    def summary(self, name):
        """{"ratio": 0~1, "run_sec", "now_sec", "segments": [(시작초, 끝초, "RUN"|"ALARM"), …]}"""
        now_sec = max(1, _sec(datetime.datetime.now()))
        ev = self.events.get(name, [])
        run, segs = 0, []
        for i, (t, st) in enumerate(ev):
            end = ev[i + 1][0] if i + 1 < len(ev) else now_sec
            if st in ("RUN", "ALARM") and end > t:
                segs.append((t, end, st))
            if st == "RUN":
                run += max(0, end - t)
        return {"ratio": run / now_sec, "run_sec": run, "now_sec": now_sec, "segments": segs}
