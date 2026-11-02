"""[v3.0] 지난날 통계 — logs/ CSV(가공 이력·알람 이력·가동 상태)만 읽어서 계산한다 (장비에는 접근하지 않음).
PC 화면(js_api)과 휴대폰 페이지(원격 서버)의 이력·통계 탭, 가공 이력 탭 맨 위 '그날 요약'이 함께 쓴다."""
import os
import re
import csv
import datetime
from notifier import hms_sec, row_minor
from utilization import day_summary

WEEKDAYS = "월화수목금토일"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")   # 날짜 값 검증 (경로 조작 방지 — 휴대폰에서도 들어오는 값)


def _rows(log_dir, name):
    if not log_dir:
        return []
    try:
        with open(os.path.join(log_dir, name), newline="", encoding="utf-8-sig") as f:
            return list(csv.reader(f))[1:]
    except OSError:
        return []


def _day(date):
    """(볼 날짜, 오늘). 날짜가 없거나 형식이 틀리면 오늘"""
    today = datetime.date.today().isoformat()
    return (date if date and DATE_RE.match(str(date)) else today), today


def history(log_dir, date=None, order=()):
    """그날 가공 이력(최신순) + 그날 요약. 정지 시간·프로그램·결과 열은 v3.0부터 있다 (예전 5열 행은 정지 0, 완료로)"""
    date, today = _day(date)
    rows = [{"machine": r[1], "start": r[2], "end": r[3], "cycle": r[4], "pause": r[5] if len(r) > 5 else "",
             "program": r[6] if len(r) > 6 else "", "result": r[7] if len(r) > 7 else "완료", "minor": row_minor(r)}
            for r in reversed(_rows(log_dir, f"history_{date}.csv")) if len(r) >= 5]
    return {"date": date, "today": today, "rows": rows, "summary": day_detail(log_dir, date, order) if log_dir else []}


def alarms(log_dir, date=None):
    """그날 알람 발생·해제 (최신순)"""
    date, today = _day(date)
    rows = [{"time": r[1], "machine": r[2], "kind": r[3], "code": r[4], "msg": r[5]}
            for r in reversed(_rows(log_dir, f"alarm_{date}.csv")) if len(r) >= 6]
    return {"date": date, "today": today, "rows": rows}


def day_counts(log_dir, date):
    """{장비명: {"count": 완료 횟수, "cut_sec": 가공 시간 합, "alarms": 알람 발생 수}}. 짧은 가공(notifier.is_minor)은 빼고 센다"""
    out = {}
    blank = lambda: {"count": 0, "cut_sec": 0, "alarms": 0}
    for r in _rows(log_dir, f"history_{date}.csv"):
        if len(r) < 5:
            continue
        m = out.setdefault(r[1], blank())
        if row_minor(r):
            continue
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
