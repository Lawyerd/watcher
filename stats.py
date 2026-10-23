"""[v3.0] 지난날 통계 — logs/ CSV(가공 이력·알람 이력·가동 상태)만 읽어서 계산한다 (장비에는 접근하지 않음).
휴대폰 페이지의 '통계' 탭(최근 N일)과 가공 이력 탭 맨 위 '그날 요약'이 쓴다."""
import os
import csv
import datetime
from notifier import hms_sec
from utilization import day_summary

WEEKDAYS = "월화수목금토일"


def _rows(log_dir, name):
    try:
        with open(os.path.join(log_dir, name), newline="", encoding="utf-8-sig") as f:
            return list(csv.reader(f))[1:]
    except OSError:
        return []


def day_counts(log_dir, date):
    """{장비명: {"count": 완료 횟수, "cut_sec": 가공 시간 합, "alarms": 알람 발생 수}}"""
    out = {}
    blank = lambda: {"count": 0, "cut_sec": 0, "alarms": 0}
    for r in _rows(log_dir, f"history_{date}.csv"):
        if len(r) < 5:
            continue
        m = out.setdefault(r[1], blank())
        m["cut_sec"] += hms_sec(r[4])                      # 사이클 타임 = 멈춘 시간을 뺀 순수 가공 시간
        m["count"] += 0 if len(r) >= 8 and r[7] == "알람" else 1
    for r in _rows(log_dir, f"alarm_{date}.csv"):
        if len(r) >= 4 and r[3] == "발생":
            out.setdefault(r[2], blank())["alarms"] += 1
    return out


def day_detail(log_dir, date, order=()):
    """그날 요약: 장비별 횟수·가공 시간·알람 + 가동률(상태 기록이 있는 날만, v3.0 이후)"""
    counts, util = day_counts(log_dir, date), day_summary(log_dir, date)
    names = [n for n in order if n in counts or n in util] + sorted((set(counts) | set(util)) - set(order))
    return [dict(counts.get(n, {"count": 0, "cut_sec": 0, "alarms": 0}), machine=n, util=util.get(n)) for n in names]


def recent(log_dir, days, order=()):
    """최근 days일(오늘 포함, 최신순) 날짜별 장비 통계"""
    today = datetime.date.today()
    out = []
    for i in range(days):
        d = today - datetime.timedelta(days=i)
        c = day_counts(log_dir, d.isoformat())
        out.append({"date": d.isoformat(), "weekday": WEEKDAYS[d.weekday()], "machines": c})
    names = list(order) + sorted({n for day in out for n in day["machines"]} - set(order))
    return {"days": out, "machines": names}
