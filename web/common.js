// ── 휴대폰·PC 공통 (webui.py가 두 화면의 COMMON_JS 자리에 넣는다) ──
// 상태별 [글자·막대 색, 배경 색] — 실제 색 값은 common.css 변수
const C = { RUN: ["var(--green)", "var(--green-bg)"], ALARM: ["var(--red)", "var(--red-bg)"], HOLD: ["var(--yellow)", "var(--yellow-bg)"],
            IDLE: ["var(--gray)", "var(--btn)"], OFFLINE: ["var(--off)", "var(--off-bg)"] };
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

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
