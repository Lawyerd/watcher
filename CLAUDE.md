# CNC Watcher

FANUC CNC 장비(DN Solutions DVF5000/DVF6500)를 FOCAS 라이브러리로 실시간 모니터링하는 Windows 데스크톱 앱.
퇴근 후에도 휴대폰 브라우저로 상태를 볼 수 있게 원격 모니터링(읽기 전용 웹 페이지 + PIN 로그인, Tailscale Funnel 공개)을 내장.
현재 버전 **v3.0** (2026-10-22, `main`). Python + **pywebview(WebView2)** 화면, PyInstaller로 exe 배포.
v2.4까지는 Tkinter/customtkinter 화면이었다 (Tk는 애니메이션이 초당 30장·폴링 때 끊겨서 웹 화면으로 전환, 이전 코드는 git 기록 `09b3145`).

## 구조

```
[장비 스레드 poller.py] ── FOCAS 연결·읽기·재연결, 알림·CSV·가동률, 원격 서버 켜기/끄기
        │ snapshot()/pop_events()            │ update_snapshot() (IP 제외)
        ▼                                     ▼
[PC 화면 web/desktop.html] ◀─ js_api ─▶ [main.py Api]      [remote_server.py :8765] ─▶ 휴대폰 (web/phone.html)
  (pywebview 창, 0.5초마다 status 조회)   (창 조작·설정·PIN)     (PIN 로그인, Funnel로 인터넷 공개 가능)
```

| 파일 | 역할 |
|---|---|
| `main.py` | 진입점. `App`(pywebview 창·트레이·종료 처리), `Api`(PC 화면 → 파이썬 호출 창구: 연결/해제, 알림, 원격·PIN, 설정 창(장비·자동 실행), 창 조작), 아이콘 생성, 중복 실행 방지, `--selftest`, `--tray`(숨겨서 시작) |
| `poller.py` | **장비 전용 스레드** (`Poller`). FOCAS 전부 + `notifier`·`utilization` 호출 + 스냅샷 생성 + 원격 서버 시작/정지 + 연결 상태 기억(`connections.json`). 화면은 `request()`로 명령만 넣는다 |
| `web/desktop.html` | PC 화면 (HTML/CSS/JS 한 장). 헤더(📡⚙🔔 최소화 모드 — ✕), 장비 카드, 알람 목록, 부하·가동률 펼침 패널(CSS 전환), 설정 창(장비 + 일반: 자동 실행)·원격 PIN 창·알람 팝업(모달), 최소화 모드, 툴팁 |
| `web/phone.html` | 휴대폰 페이지 (숫자 키패드 PIN 로그인 → 가동/정지/알람 타일 + 현황/가공 이력/알람 이력 탭, 장비를 누르면 부하·가동률). `manifest.webmanifest`와 함께 원격 서버가 응답 |
| `web/common.css`, `web/common.js` | 두 화면 공통: **다크 팔레트(`:root` 변수)**, 상태 색 `C`, `esc`, 부하 막대 색·폭, 가동률 문구·타임라인 |
| `webui.py` | `web/` 파일 읽기. 각 화면의 `/*@COMMON_CSS@*/`·`/*@COMMON_JS@*/`(+ PC는 `/*@FONTS@*/`) 자리에 공통 파일을 끼워 넣는다 |
| `startup.py` | 윈도우 시작 시 자동 실행 (HKCU `Run` 레지스트리, exe일 때만) |
| `fanuc_logic.py` | FOCAS 통신 (`FanucMachine`). 상태/사이클타임(파라미터 6757·6758)/공구번호(PMC D0450·D0452)/알람/스핀들·축 부하(`cnc_rdspmeter`·`cnc_rdsvmeter`, 회전수 `cnc_acts`)/실행 프로그램명(`cnc_exeprgname`, 선택 없음·MDI는 "O0"→None) 읽기 |
| `notifier.py` | 상태 전이 감지 → winotify 토스트 + `logs/history_YYYY-MM-DD.csv` 가공 이력 + `logs/alarm_YYYY-MM-DD.csv` 알람 발생/해제 이력 기록 |
| `utilization.py` | 가동률 (`UtilizationTracker`). 상태 변화를 `logs/state_YYYY-MM-DD.csv`에 기록, 오늘 0시부터 RUN 비율·타임라인 구간 계산 |
| `remote_server.py` | 원격 모니터링 (`RemoteServer`). 읽기 전용 HTTP 서버(포트 8765): `/api/status`(스냅샷), `/api/history`·`/api/alarms`(`?date=`로 logs/ CSV), 홈 화면 아이콘·manifest. `/api/*`는 PIN 로그인 필요(`RemoteAuth`, `remote.json`에 PIN 해시·쿠키 서명 키). 켜져 있는 동안 시스템 절전 차단 |
| `machines.json` | 장비 목록 (앱 내 ⚙ 설정 창으로 편집, 재시작 불필요) |
| `remote.json`, `connections.json`, `logs/`, `cnc_watcher.log` | 실행 시 exe 옆에 생기는 런타임 파일 (PIN 해시 / 꺼질 때 연결돼 있던 장비 / CSV 이력: history·alarm·state / 로그). 모두 gitignore |
| `read_status.py`, `connection_test.py` | 단독 연결 테스트 스크립트 |

## 반드시 알아야 할 제약 (고생해서 알아낸 것들)

### FOCAS·장비
1. **FOCAS 핸들은 만든 스레드에서만 유효.** 다른 스레드에서 쓰면 EW_HANDLE(-8). → v3.0은 `Poller` 스레드 하나가 연결·읽기·재연결·**해제(종료 시 포함)**까지 전부 한다. 화면(js_api 스레드)·원격 서버 스레드에서 FOCAS 함수를 절대 직접 부르지 말고 `poller.request()`로 명령만 넣을 것.
2. **절전 복귀 시 FOCAS 함수가 음수 오류(-16 EW_SOCKET 등)를 반환** → `fetch_data`에서 ret != 0이면 `drop_connection()` 후 자동 재연결(10초 간격)에 맡김. 오류를 무시하면 화면이 옛날 값으로 멈춘다.
3. **공구번호는 매크로 #4120이 아니라 PMC D0450(스핀들)/D0452(대기 포트)에서 읽는다.** #4120은 '마지막 지령 T코드'라 T 선지령 시 대기 공구가 나옴. D0450은 DN Solutions PMC 주소로 DVF5000/6500에서 실측 확인(M06마다 D0450↔D0452 교환, 매거진 포트 테이블 D3302~D3420에서 스핀들 공구만 빠져 있음). 다른 기종 추가 시 재확인 필요.
4. **알람 내용은 `cnc_rdalmmsg2`로 알람 상태(`stat.alarm`)일 때만 읽는다.** 발생 시각은 FOCAS가 주지 않아 처음 본 시각을 유지. 장비 화면이 한글 설정이라 메시지가 cp949로 내려옴 (`#3000=1` 테스트 → "MC3001 매크로 알람" 실측 확인). 알람 이력 조회 함수(`cnc_rdalmhistry` 류)는 이력 기록 정지가 필요할 수 있어 사용하지 않음.
5. **축 구성은 기계마다 다르다** (DVF5000 = X·Y·Z·C·B, DVF6500 = X·Y·Z·C·A, 3축기 = X·Y·Z). 축 이름·개수를 하드코딩하지 말고 `cnc_rdsvmeter`가 돌려주는 이름을 그대로 쓴다. 빈 슬롯(`\x00`)이 섞여 오므로 걸러낼 것. Z축은 정지 중에도 40~55%(주축 무게 지지)로 나오는 게 정상.
6. 장비당 FOCAS 읽기 한 바퀴 약 17ms (2대 ≈ 32ms). v2.4까지는 이게 화면 스레드를 막아 끊김의 원인이었다.

### 알림·이력
7. **plyer 토스트는 Win11에서 오류 없이 무시됨.** winotify(네이티브 토스트) 사용, plyer는 폴백. 토스트 아이콘은 256px PNG 필요 (`icons/watcher_icon.png`).
8. 알림 토글(🔕)은 토스트만 끈다. **CSV 가공 이력은 항상 기록**. OFFLINE 전이는 가공 이벤트로 취급하지 않음 (가짜 '가공 완료' 방지).
9. **가동률은 앱이 켜져 있던 동안만 안다.** 1분마다 state CSV 수정 시각을 갱신(하트비트)하고, 다음 실행 때 그 시각 이후를 OFFLINE으로 넣어 비정상 종료 후 마지막 상태가 계속 이어진 것으로 계산되는 걸 막는다. 정상 종료 시 OFFLINE으로 마감.
10. 중복 실행 방지: 127.0.0.1:54321 포트 바인딩 (`--selftest`는 예외).

### 화면 (pywebview / WebView2)
11. **제어 기능(연결·설정·PIN)은 js_api로만, 절대 HTTP로 열지 말 것.** 원격 서버(8765)는 Funnel로 인터넷에 공개되고, Funnel 요청은 127.0.0.1에서 온 것처럼 보여 로컬/외부를 구분할 수 없다.
12. **js_api 메서드는 매번 새 스레드에서 실행된다.** 그래서 ① FOCAS 금지(1번) ② 절전 차단(`SetThreadExecutionState`)은 호출 스레드가 살아 있는 동안만 유지되므로 원격 켜기/끄기는 `poller.request("remote_start"/"remote_stop")`로 장비 스레드에서 한다.
13. **pywebview `window.on_top`을 다른 스레드에서 쓰면 데드락** — .NET 속성을 GIL을 쥔 채 바꾸고, 화면 스레드는 GIL을 기다린다(실측: 최소화 모드 전환에서 멈춤). `App.set_topmost()`처럼 Win32 `SetWindowPos(..., SWP_ASYNCWINDOWPOS)`로 직접 한다. `resize`/`move`는 내부가 ctypes라 괜찮고, `show/hide/minimize/restore`는 Invoke라 괜찮다. pythonnet으로 창 속성을 직접 바꾸는 코드는 피할 것.
14. **폰트는 PC 화면 html에 base64로 넣는다** (`build_html`, `/*@FONTS@*/` 자리. 휴대폰은 기기 기본 고정폭 글꼴). WebView2 렌더러는 별도 프로세스라 파이썬에서 `AddFontResourceEx`로 등록한 폰트를 못 쓰고, html 문자열로 띄우므로 파일 경로도 못 쓴다. `fonts/` 폴더(OFL.txt 포함)는 exe 옆에 두어야 한다.
15. **창 높이는 화면이 내용을 재서 `api.fit()`으로 맞춘다.** 펼칠 땐 애니메이션 전에 늘리고 접을 땐 끝난 뒤 줄인다(움직이는 중엔 재지 않음). 모달이 창보다 크면 모달 높이만큼 임시로 늘린다(`minHeight`). 모달 내용을 연 뒤에 채우거나 바꾸면 `fitModal()`을 다시 불러야 잘리지 않는다.
16. 닫기(✕)와 Alt+F4는 **종료가 아니라 트레이로 숨김** (`closing` 이벤트에서 `hide()` 후 `False` 반환으로 취소). 종료는 트레이 메뉴 '종료'만.
17. 최소화 모드 카드 끌기는 `api.compact_drag()`가 마우스 버튼을 놓을 때까지 창을 따라 움직이고 이동 거리를 돌려준다 — 4px 미만이면 '클릭'으로 보고 원래 크기로.

### 원격 접속
18. **원격 접속 방화벽**: 공장 PC 네트워크는 "공용", Tailscale 어댑터는 "개인"으로 잡힌다. exe별 허용 규칙은 버전마다 경로가 바뀌므로 포트 규칙(8765, 원격 IP 100.64.0.0/10)으로 허용하는 게 안정적.
19. **원격 페이지는 Tailscale Funnel로 인터넷에 공개될 수 있다** (`tailscale funnel --bg 8765` → `https://기기.tailnet.ts.net`). 그래서 PIN 없이는 서버를 켤 수 없게 했고(📡 → PIN 설정 창), 페이지·아이콘 외 모든 `/api/*`는 로그인 쿠키(30일, HMAC 서명) 필요. PIN 5회 실패 시 5분 잠금. 휴대폰 스냅샷에는 장비 IP·포트를 넣지 않는다.
20. **PIN 기능 이전 빌드로 📡를 켜면 Funnel을 통해 PIN 없이 공개된다** (2026-10-21 실제로 발생 → exe 종료 후 재빌드로 해결). Funnel이 켜진 PC에서는 반드시 PIN 기능이 들어간 빌드만 실행할 것. 앱의 📡가 꺼져 있으면 Funnel 주소는 502가 된다(정상).

### 자동 실행·상태 기억
21. **자동 실행은 HKCU `Run` 값 하나**(`CNC Watcher` = `"exe 경로" [--tray]`). 관리자 권한 불필요, 윈도우 **로그인 후** 실행된다. '트레이로 숨겨서 시작'은 `--tray` 인자로 기억(별도 파일 없음). 버전마다 dist 폴더가 달라 경로가 바뀌므로, 켜져 있으면 실행할 때마다 지금 exe로 갱신(`follow_current_exe`) — 예전 빌드(특히 PIN 이전 빌드, 20번)가 자동 실행되지 않게. `python main.py`에서는 끌 수도 켤 수도 없다(스위치 흐림). `--selftest`는 레지스트리를 건드리지 않는다.
22. **자동 실행 때 작업 폴더는 system32** → 로그 등 모든 경로는 `BASE_DIR` 기준 절대 경로로 쓸 것 (상대 경로 `cnc_watcher.log`였다가 고침).
23. **상태 기억은 장비 연결만** (사용자 선택 — 📡 원격·🔔 알림·창 위치는 기억하지 않음, 📡는 재시작 후 다시 눌러야 함). `want_connected`가 바뀔 때마다 `connections.json`에 저장하고, 시작 시 그 장비들을 바로 connect하지 않고 **자동 재연결 대상(`want_connected=True`)으로 둔다** — 부팅 직후 장비가 아직 꺼져 있어도 오류 팝업 없이 10초마다 다시 붙는다. 종료(shutdown) 때 해제는 저장하지 않는다.
24. `hidden=True`(트레이로 시작)여도 WebView2 화면(JS)은 돈다 — 상태 조회·알람 팝업(`attention()`) 정상. 숨김 중엔 타이머가 약 1초로 느려진다(실측).

## 원격 접속 (휴대폰) 운영

- **구성**: 휴대폰 브라우저 → `https://junseok.tail3497b8.ts.net` (Tailscale Funnel) → 이 PC의 tailscaled → `127.0.0.1:8765` (CNC Watcher 📡). 휴대폰에는 앱 설치 불필요, 첫 접속 때 PIN 6자리 입력.
- **회사 PC 설정** (한 번만): Tailscale 설치·로그인, Preferences → **Run unattended**, 관리 화면 Machines → **Disable key expiry**(안 하면 180일 뒤 Funnel 중단), DNS → **HTTPS Certificates** 켜기, `tailscale funnel --bg 8765`(재부팅해도 유지, 끄기는 `tailscale funnel --https=443 off`).
- **Tailscale 정책 (Access controls)**: `hosts`에 `cnc-pc: 100.98.49.15`, `acls`는 `cnc-pc:8765`와 `cnc-pc:443`만 허용, `nodeAttrs`로 `funnel` 허용. **443을 빼면 휴대폰에 Tailscale이 켜져 있을 때 https 주소가 내부 경로로 가서 막혀 빈 화면이 뜬다** (실제로 겪음).
- **PC를 바꾸면** 새 PC에서 위 설정을 다시 하고, 주소(기기 이름)와 ACL의 `cnc-pc` IP가 바뀐다. PIN도 PC마다 `remote.json`에 따로 저장된다.
- **외부 경로 확인 방법**: 이 PC에서는 MagicDNS 때문에 `Resolve-DnsName -Server 8.8.8.8`도 100.x를 돌려준다. 공개 DNS는 `https://dns.google/resolve?name=<호스트>&type=A`로 보고, 실제 외부 경로는 `curl --resolve <호스트>:443:<중계 IP> https://<호스트>/api/status`로 확인(로그인 없으면 401이 정상).
- 휴대폰 분실·교체 시 PC에서 **📡 우클릭 → 모든 기기 로그아웃** (서명 키 교체로 기존 쿠키 전부 무효).

## 빌드 & 배포

```bash
pyinstaller CNC_Watcher_v3.0.spec --noconfirm && cp -r dll icons fonts dist/CNC_Watcher_v3.0/ && cp machines.json dist/CNC_Watcher_v3.0/
```

- spec이 없으면 아래로 만든다. **pywebview가 쓰지도 않는 Qt(PySide6) 화면 엔진을 끌고 와 644MB가 되므로 제외 목록이 필수** (빼면 약 63MB).
  ```bash
  pyinstaller --noconfirm --windowed --name CNC_Watcher_v3.0 --icon icons/watcher_icon.ico --add-data "web;web" --exclude-module PySide6 --exclude-module shiboken6 --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module qtpy --exclude-module webview.platforms.qt --exclude-module webview.platforms.gtk --exclude-module webview.platforms.cef --exclude-module webview.platforms.cocoa --exclude-module webview.platforms.android --exclude-module numpy --exclude-module cryptography --exclude-module cv2 --exclude-module customtkinter main.py
  ```
- 필요한 패키지: `pywebview`(6.x), `pythonnet`, `pystray`, `Pillow`, `winotify`. 실행 PC에는 **WebView2 런타임**(윈도우 11 기본 포함, 윈도우 10은 별도 설치)과 .NET Framework 4.7.2+ 필요.
- `web/` 폴더 전체(PC·휴대폰 화면, 공통 파일)는 exe 안(`_internal/web`)에 묶이고, `dll/ icons/ fonts/ machines.json`은 exe 옆에 복사한다.
- **재빌드하면 dist 폴더가 초기화되므로 dll/icons/fonts/machines.json 복사를 매번 다시 해야 한다.**
- dist에서 exe를 실행하며 생긴 `logs/`(가공·알람·가동률 이력), `remote.json`(원격 PIN), `connections.json`(연결 상태), `machines.json`(앱에서 장비를 바꿨으면 프로젝트 것과 다름)도 같이 지워지므로 **재빌드 전에 백업 → 빌드 후 복원**. 셸 작업 위치가 dist 폴더 안이면 폴더 삭제가 막혀 빌드가 실패한다.
- 빌드 전 실행 중인 exe를 종료할 것 (dll 잠김으로 빌드 실패).
- `dist\CNC_Watcher_v3.0\` 폴더 전체가 완전한 배포본 — 공장 PC에 폴더째 복사하면 끝.
- `*.spec`은 gitignore 대상(로컬 전용). 버전 올릴 때 `main.py`의 `VERSION`도 같이 올릴 것.

## 테스트 방법

- **자가 테스트**: `python main.py --selftest` (또는 exe에 같은 인자, `--tray`를 더하면 숨겨서 시작한 경우 점검). 실장비 연결 → 카드 펼치기/접기(FPS 측정) → 최소화 모드 → 설정 창 → 원격 PIN 창 → 알람 팝업(가짜) → 숨기기/트레이 열기/Alt+F4 순서로 돌고, 각 화면을 임시 폴더에 캡처(캡처 순간만 맨 위로)한 뒤 결과를 `cnc_watcher.log`에 `[자가 테스트]`로 남기고 종료한다. 실행 중인 앱과 같이 돌 수 있고(중복 실행 검사 생략), 이력·연결 상태는 임시 폴더·PIN은 메모리·토스트는 꺼짐·자동 실행 레지스트리는 안 건드림이라 실제 데이터를 건드리지 않는다. v3.0 기준 결과: 펼침 65~69fps, 장비 스레드 한 바퀴 약 32ms.
- FOCAS 검증: 개발 PC(= 공장 PC)에서 실장비(192.168.10.109/108, 포트 8193) 직접 접근 가능. `read_status.py` 참고.
- 실장비 연결 검증(절전 복귀, 가공 완료 알림 등)은 사용자만 가능 — 수정 후 사용자 확인을 기다릴 것.
- 자동 실행 함수 검증은 `startup.RUN_KEY`를 테스트용 키(예: `Software\CNCWatcherTest\Run`)로 바꿔서 하고 끝나면 지울 것 — 진짜 `Run` 키는 사용자가 설정 창에서만 바꾼다.
- 원격 서버 검증: `RemoteServer(host="127.0.0.1", port=87xx, auth=RemoteAuth())`처럼 **localhost + 메모리 전용 인증**으로 띄울 것 (0.0.0.0 바인딩은 방화벽 팝업, 기본 경로는 `remote.json` 생성). `Poller`에 그 서버를 넣고 `request("remote_start")`하면 실장비 스냅샷까지 확인된다. 휴대폰 화면은 브라우저 모바일 뷰포트(375×812)로 확인.
- 실행 중인 exe/`python main.py`가 있으면 새로 띄운 앱은 "이미 실행 중"으로 멈춘다 (`--selftest` 제외).
- 콘솔 출력은 cp949라 한글이 깨진다 — 결과는 `cnc_watcher.log`(UTF-8)로 볼 것.

## 컨벤션

- 소통·주석·커밋 메시지 한국어 (진행 보고·요약·질문 포함, 영어 화면 캡처를 받아도 답은 한국어). 커밋은 이모지 접두사: `🎨 design:` `🐛 fix:` `🔧 feature/chore:` `📦 feature:`
- UI 변경은 코드보다 **목업 시안(2~4개)을 먼저** 보여주고 사용자가 고른 뒤 구현. 구현 후 스크린샷으로 확인시키고, 사용자가 "커밋해줘" 하면 커밋·푸시.
- 색상은 `web/common.css`의 `:root` 변수 한 곳 (PC·휴대폰 공통). JS에서 색을 쓸 때도 `var(--green)`처럼 변수로 — 상태 색은 `common.js`의 `C`. 화면 하나에만 쓰는 장식 색(알람 팝업 등)만 각 html에 둔다.
