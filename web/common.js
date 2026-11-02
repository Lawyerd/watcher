// ── 휴대폰·PC 공통 (webui.py가 두 화면의 COMMON_JS 자리에 넣는다) ──
// 상태별 [글자·막대 색, 배경 색] — 실제 색 값은 common.css 변수
const C = { RUN: ["var(--green)", "var(--green-bg)"], ALARM: ["var(--red)", "var(--red-bg)"], HOLD: ["var(--yellow)", "var(--yellow-bg)"],
            IDLE: ["var(--gray)", "var(--btn)"], OFFLINE: ["var(--off)", "var(--off-bg)"] };
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

// 기계별 알림 칸: 종류 → [이름, 아이콘] (PC는 세 가지, 휴대폰은 알람·완료)
const CHIP = {
  alarm: ["알람", '<svg viewBox="0 0 24 24"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>'],
  done: ["완료", '<svg viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg>'],
  pause: ["정지", '<svg viewBox="0 0 24 24"><path d="M8 5v14M16 5v14"/></svg>'],
};
const chipHtml = (name, kind, on, disabled) => `<button class="chip chip-${kind}${on ? " on" : ""}" data-name="${esc(name)}" data-kind="${kind}"${disabled ? " disabled" : ""} aria-label="${esc(name)} ${CHIP[kind][0]}">${CHIP[kind][1]}</button>`;

// 부하 막대: 0~150% 눈금, 80% 이상 노랑 · 100% 이상 빨강
const loadCol = p => p == null ? "var(--sub)" : p >= 100 ? "var(--red)" : p >= 80 ? "var(--yellow)" : "var(--green)";
const loadWidth = p => Math.min(p || 0, 150) / 1.5 + "%";
const pctText = p => p == null ? "-" : p + "%";

// 오늘 가동률 (utilization.py summary: ratio, run_sec, now_sec, segments)
const utilPct = u => Math.round(u.ratio * 100) + "%";
function runText(u) {
  const mins = Math.floor(u.run_sec / 60), h = Math.floor(mins / 60);
  return "가공 " + (h ? `${h}시간 ${mins % 60}분` : `${mins}분`);
}
const timelineHtml = u => u.segments.map(([s, e, st]) =>
  `<i style="left:${s / u.now_sec * 100}%;width:${Math.max((e - s) / u.now_sec * 100, .4)}%;background:${C[st][0]}"></i>`).join("");

// 완료 예상 (notifier.eta): 돌아가는 중이면 시각까지, 멈춰 있으면 남은 시간만
function hm(sec) {
  const m = Math.floor(sec / 60), h = Math.floor(m / 60);
  return h ? `${h}시간 ${m % 60}분` : `${m}분`;
}
const etaLeft = e => "남은 " + hm(Math.ceil(e.left / 60) * 60);
const etaText = e => !e ? "" : e.at ? `약 ${e.at} 완료 · ${etaLeft(e)}` : etaLeft(e);

// ── 이력·통계 (PC·휴대폰 공통) ──
// 시작→끝 중 가공하지 않은 시간 (M00·M01·싱글 블록·피드 홀드) — 사이클 타임은 순수 가공 시간
function pauseLabel(p) {
  const s = p ? p.split(":").reduce((a, x) => a * 60 + +x, 0) : 0;
  if (!s) return "";
  const m = Math.floor(s / 60), h = Math.floor(m / 60);
  return h ? `${h}시간 ${m % 60}분` : m ? `${m}분 ${s % 60}초` : `${s}초`;
}
const rowTag = r => r.result === "알람" ? `<span class="atag">알람</span>` : r.minor ? `<span class="mtag">횟수 제외</span>` : "";

// 그날 요약: 장비별 가동률·타임라인(상태 기록이 있는 날만)·가공 횟수·가공 시간·알람
function daySummaryHtml(list, isToday) {
  if (!list.length) return "";
  const end = isToday ? "지금" : "24시";
  return `<div class="daysum">${list.map(s => `<div class="ds">
    <div class="dsh"><b>${esc(s.machine)}</b>${s.util ? `<span class="dsv">가동률 <b>${utilPct(s.util)}</b></span>` : ""}</div>
    ${s.util ? `<div class="tl">${timelineHtml(s.util)}</div><div class="tlx"><span>0시</span><span>${end}</span></div>` : ""}
    <div class="dsv">가공 <b>${s.count}회</b> · <b>${hm(s.cut_sec)}</b> · 알람 <b>${s.alarms}회</b></div></div>`).join("")}</div>`;
}

// 통계: 7일·30일 고르는 칸 + 하루 가공 시간 막대 (막대·날짜를 누르면 그날 가공 이력, data-date)
const MC = ["var(--green)", "var(--m2)", "var(--m3)", "var(--m4)"];
const statSeg = cur => `<div class="seg">${[7, 30].map(n => `<button data-days="${n}"${n === cur ? ' class="on"' : ""}>${n}일</button>`).join("")}</div>`;
function statChartHtml(data, cur) {
  const names = data.machines, days = [...data.days].reverse();   // 그래프는 오래된 날 → 오늘
  const cut = (x, n) => (x.machines[n] || {}).cut_sec || 0;
  const max = Math.max(60, ...days.flatMap(x => names.map(n => cut(x, n))));
  const d30 = cur === 30 ? " d30" : "";
  return `<div class="pcard"><div class="legend">하루 가공 시간 ${names.map((n, i) => `<span><i style="background:${MC[i % 4]}"></i>${esc(n)}</span>`).join("")}</div>
    <div class="chart${d30}"><span class="ymax">${hm(max)}</span>${days.map(x =>
      `<div class="bg" data-date="${x.date}">${names.map((n, i) => `<i style="height:${cut(x, n) / max * 100}%;background:${MC[i % 4]}"></i>`).join("")}</div>`).join("")}</div>
    <div class="cx mono${d30}">${days.map((x, i) => `<span>${!d30 || i % 5 === 0 || i === days.length - 1 ? +x.date.slice(8) : ""}</span>`).join("")}</div></div>`;
}
const dayTotal = (x, names) => names.reduce((a, n) => { const m = x.machines[n] || {}; a.c += m.count || 0; a.s += m.cut_sec || 0; a.a += m.alarms || 0; return a; }, { c: 0, s: 0, a: 0 });
