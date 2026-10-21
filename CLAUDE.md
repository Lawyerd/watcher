# CNC Watcher

FANUC CNC 장비(DN Solutions DVF5000/DVF6500)를 FOCAS 라이브러리로 실시간 모니터링하는 Windows 데스크톱 앱.
퇴근 후에도 휴대폰 브라우저로 상태를 볼 수 있게 원격 모니터링(읽기 전용 웹 페이지 + PIN 로그인, Tailscale Funnel 공개)을 내장.
현재 버전 **v2.4** (2026-10-21 빌드). Python + customtkinter, PyInstaller로 exe 배포.

## 파일 구조

| 파일 | 역할 |
|---|---|
| `main.py` | 진입점 + MainController. 폴링 루프(보임 0.5s / 숨김 3s), 자동 재연결, 트레이, 설정 저장, 아이콘 생성 |
| `fanuc_logic.py` | FOCAS 통신 (`FanucMachine`). 상태/사이클타임(파라미터 6757·6758)/공구번호(PMC D0450·D0452) 읽기 |
| `monitor_ui.py` | UI 전부 (`AppUI`, `SettingsDialog`, `RemoteDialog`(📡 PIN 설정 창), 다크 테마 팔레트). 상태 반영은 `AppUI.apply_status()` 한 곳으로 일원화. 기본 타이틀바 없음(헤더가 타이틀바), 알람 시 카드에 알람 목록 펼침 + 창 높이 자동(`fit_height`) |
| `notifier.py` | 상태 전이 감지 → winotify 토스트 + `logs/history_YYYY-MM-DD.csv` 가공 이력 + `logs/alarm_YYYY-MM-DD.csv` 알람 발생/해제 이력 기록 |
| `remote_server.py` | 원격 모니터링 (`RemoteServer`). 읽기 전용 HTTP 서버(포트 8765): `/api/status`(스냅샷), `/api/history`·`/api/alarms`(`?date=`로 logs/ CSV), 홈 화면 아이콘·manifest. `/api/*`는 PIN 로그인 필요(`RemoteAuth`, `remote.json`에 PIN 해시·쿠키 서명 키). 켜져 있는 동안 시스템 절전 차단 |
| `remote_page.py` | 휴대폰 페이지 HTML 한 장 (숫자 키패드 PIN 로그인 → 가동/정지/알람 타일 + 현황/가공 이력/알람 이력 탭) |
| `machines.json` | 장비 목록 (앱 내 ⚙️ 설정 UI로 편집 가능, 재시작 불필요) |
| `remote.json`, `logs/`, `cnc_watcher.log` | 실행 시 exe 옆에 생기는 런타임 파일 (PIN 해시 / CSV 이력 / 로그). 모두 gitignore |
| `read_status.py`, `connection_test.py` | 단독 연결 테스트 스크립트 |

## 반드시 알아야 할 제약 (고생해서 알아낸 것들)

1. **FOCAS 핸들은 만든 스레드에서만 유효.** 다른 스레드에서 쓰면 EW_HANDLE(-8).
   → 자동 재연결은 백그라운드 스레드에서 TCP 프로브만 하고, 실제 `cnc_allclibhndl3`는 `app.after(0, ...)`로 메인 스레드에서 실행 (`main.py try_reconnect/_finish_reconnect`). 절대 백그라운드에서 FOCAS 함수를 호출하지 말 것.
2. **절전 복귀 시 FOCAS 함수가 음수 오류(-16 EW_SOCKET 등)를 반환** → `fetch_data`에서 ret != 0이면 `drop_connection()` 후 자동 재연결에 맡김. 오류를 무시하면 화면이 옛날 값으로 멈춘다.
3. **plyer 토스트는 Win11에서 오류 없이 무시됨.** winotify(네이티브 토스트) 사용, plyer는 폴백. 토스트 아이콘은 256px PNG 필요 (`icons/watcher_icon.png`).
4. **CTkFrame 기본 크기가 200×200.** 얇은 스트립 등을 만들 때 `height=10` 같은 최소값을 명시하지 않으면 레이아웃이 부푼다.
5. **customtkinter는 Toplevel 생성 200ms 후 기본 아이콘으로 덮어씀** → `after(250, lambda: win.iconbitmap(...))`로 재적용 (SettingsDialog, RemoteDialog, 알람 팝업).
6. **JetBrains Mono는 fonts/ 폴더로 동봉 배포** — `AddFontResourceEx(FR_PRIVATE)`로 프로세스 전용 로드(`load_private_fonts()`), 시스템 설치 불필요. 폰트 폴백: JetBrains Mono → Cascadia Mono → Consolas. OFL.txt 라이선스 파일 필수 동봉.
7. **최소화(슬림) 모드 창 높이는 계산식이 아니라 실측** — `update_idletasks()` 후 `scroll.winfo_reqheight()` 사용.
8. 알림 토글(🔕)은 토스트만 끈다. **CSV 가공 이력은 항상 기록**. OFFLINE 전이는 가공 이벤트로 취급하지 않음 (가짜 '가공 완료' 방지).
9. 중복 실행 방지: 127.0.0.1:54321 포트 바인딩.
10. **공구번호는 매크로 #4120이 아니라 PMC D0450(스핀들)/D0452(대기 포트)에서 읽는다.** #4120은 '마지막 지령 T코드'라 T 선지령 시 대기 공구가 나옴. D0450은 DN Solutions PMC 주소로 DVF5000/6500에서 실측 확인(M06마다 D0450↔D0452 교환, 매거진 포트 테이블 D3302~D3420에서 스핀들 공구만 빠져 있음). 다른 기종 추가 시 재확인 필요.
11. **원격 서버 스레드에서 FOCAS 호출 금지** (1번 제약). 메인 루프가 `publish_snapshot()`으로 넘긴 스냅샷만 응답한다. 절전 차단(`SetThreadExecutionState`)은 호출한 스레드 기준이라 메인 스레드에서 호출.
12. **테두리 없는 창**: `overrideredirect(True)`는 시작 시 1회만. overrideredirect 창은 작업표시줄에서 빠지고 `iconify()`가 막히므로 `_apply_frameless_style()`에서 WS_EX_APPWINDOW로 바꾸고, 최소화는 Win32 `ShowWindow(SW_MINIMIZE)`로 한다. `attributes("-topmost")`는 스타일을 유지함(실측).
13. **알람 내용은 `cnc_rdalmmsg2`로 알람 상태(`stat.alarm`)일 때만 읽는다.** 발생 시각은 FOCAS가 주지 않아 처음 본 시각을 유지. 장비 화면이 한글 설정이라 메시지가 cp949로 내려옴 (`#3000=1` 테스트 → "MC3001 매크로 알람" 실측 확인). 알람 이력 조회 함수(`cnc_rdalmhistry` 류)는 이력 기록 정지가 필요할 수 있어 사용하지 않음.
14. **원격 접속 방화벽**: 공장 PC 네트워크는 "공용", Tailscale 어댑터는 "개인"으로 잡힌다. exe별 허용 규칙은 버전마다 경로가 바뀌므로 포트 규칙(8765, 원격 IP 100.64.0.0/10)으로 허용하는 게 안정적.
15. **원격 페이지는 Tailscale Funnel로 인터넷에 공개될 수 있다** (`tailscale funnel --bg 8765` → `https://기기.tailnet.ts.net`). 그래서 PIN 없이는 서버를 켤 수 없게 했고(📡 → PIN 설정 창), 페이지·아이콘 외 모든 `/api/*`는 로그인 쿠키(30일, HMAC 서명) 필요. PIN 5회 실패 시 5분 잠금. Funnel 요청은 tailscaled가 127.0.0.1로 프록시하므로 방화벽과 무관하고, 클라이언트 IP로 사용자를 구분할 수 없다.
16. **PIN 기능 이전 빌드로 📡를 켜면 Funnel을 통해 PIN 없이 공개된다** (2026-10-21 실제로 발생 → exe 종료 후 재빌드로 해결). Funnel이 켜진 PC에서는 반드시 PIN 기능이 들어간 빌드만 실행할 것. 앱의 📡가 꺼져 있으면 Funnel 주소는 502가 된다(정상).

## 원격 접속 (휴대폰) 운영

- **구성**: 휴대폰 브라우저 → `https://junseok.tail3497b8.ts.net` (Tailscale Funnel) → 이 PC의 tailscaled → `127.0.0.1:8765` (CNC Watcher 📡). 휴대폰에는 앱 설치 불필요, 첫 접속 때 PIN 6자리 입력.
- **회사 PC 설정** (한 번만): Tailscale 설치·로그인, Preferences → **Run unattended**, 관리 화면 Machines → **Disable key expiry**(안 하면 180일 뒤 Funnel 중단), DNS → **HTTPS Certificates** 켜기, `tailscale funnel --bg 8765`(재부팅해도 유지, 끄기는 `tailscale funnel --https=443 off`).
- **Tailscale 정책 (Access controls)**: `hosts`에 `cnc-pc: 100.98.49.15`, `acls`는 `cnc-pc:8765`와 `cnc-pc:443`만 허용, `nodeAttrs`로 `funnel` 허용. **443을 빼면 휴대폰에 Tailscale이 켜져 있을 때 https 주소가 내부 경로로 가서 막혀 빈 화면이 뜬다** (실제로 겪음).
- **PC를 바꾸면** 새 PC에서 위 설정을 다시 하고, 주소(기기 이름)와 ACL의 `cnc-pc` IP가 바뀐다. PIN도 PC마다 `remote.json`에 따로 저장된다.
- **외부 경로 확인 방법**: 이 PC에서는 MagicDNS 때문에 `Resolve-DnsName -Server 8.8.8.8`도 100.x를 돌려준다. 공개 DNS는 `https://dns.google/resolve?name=<호스트>&type=A`로 보고, 실제 외부 경로는 `curl --resolve <호스트>:443:<중계 IP> https://<호스트>/api/status`로 확인(로그인 없으면 401이 정상).
- 휴대폰 분실·교체 시 PC에서 **📡 우클릭 → 모든 기기 로그아웃** (서명 키 교체로 기존 쿠키 전부 무효).

## 빌드 & 배포

```bash
pyinstaller CNC_Watcher_v2.4.spec --noconfirm && cp -r dll icons fonts dist/CNC_Watcher_v2.4/ && cp machines.json dist/CNC_Watcher_v2.4/
```

- **재빌드하면 dist 폴더가 초기화되므로 dll/icons/fonts/machines.json 복사를 매번 다시 해야 한다.**
- dist에서 exe를 실행하며 생긴 `logs/`(가공·알람 이력), `remote.json`(원격 PIN)도 같이 지워지므로 **재빌드 전에 백업 → 빌드 후 복원**. 셸 작업 위치가 dist 폴더 안이면 폴더 삭제가 막혀 빌드가 실패한다.
- 빌드 전 실행 중인 exe를 종료할 것 (dll 잠김으로 빌드 실패).
- `dist\CNC_Watcher_v2.4\` 폴더 전체가 완전한 배포본 — 공장 PC에 폴더째 복사하면 끝.
- `*.spec`은 gitignore 대상(로컬 전용). 버전 올릴 때 spec 복사 후 name/icon 수정.
- 창 제목 버전(`monitor_ui.py`의 `self.title(...)`)도 같이 올릴 것.

## 테스트 방법

- UI 검증: 가짜 머신 객체로 `AppUI`를 띄우고 `apply_status()` 호출 → PIL `ImageGrab`으로 스크린샷 (실제 장비 불필요).
- FOCAS 검증: 개발 PC에서 실장비(192.168.10.109/108, 포트 8193) 직접 접근 가능. `read_status.py` 참고.
- 실장비 연결 검증(절전 복귀, 가공 완료 알림 등)은 사용자만 가능 — 수정 후 사용자 확인을 기다릴 것.
- 원격 서버 검증: `RemoteServer(host="127.0.0.1", port=87xx, auth=RemoteAuth())`처럼 **localhost + 메모리 전용 인증**으로 띄울 것 (0.0.0.0 바인딩은 방화벽 팝업, 기본 경로는 `remote.json` 생성). 휴대폰 화면은 브라우저 모바일 뷰포트(375×812)로 확인.
- `MainController` 통합 테스트는 중복 실행 잠금을 거치지 않으므로 실행 중인 앱과 함께 돌릴 수 있다. 이때도 `c.remote_auth = c.remote.auth = RemoteAuth()`, 다른 포트(8766 등)를 쓸 것.
- 실행 중인 exe/`python main.py`가 있으면 새로 띄운 앱은 "이미 실행 중"으로 멈춘다. exe 실행 확인은 다른 창에 가려지면 `ImageGrab` 대신 `PrintWindow`로 창만 캡처.
- 빌드 결과물에 모듈이 들어갔는지는 `build/CNC_Watcher_v2.4/PYZ-00.pyz`를 `PyInstaller.archive.readers.ZlibArchiveReader`로 열어 확인.

## 컨벤션

- 소통·주석·커밋 메시지 한국어 (진행 보고·요약 포함, 영어 화면 캡처를 받아도 답은 한국어). 커밋은 이모지 접두사: `🎨 design:` `🐛 fix:` `🔧 feature/chore:` `📦 feature:`
- UI 변경은 코드보다 **목업 시안(2~4개)을 먼저** 보여주고 사용자가 고른 뒤 구현. 구현 후 스크린샷으로 확인시키고, 사용자가 "커밋해줘" 하면 커밋·푸시.
- 다크 테마 색상 팔레트는 `monitor_ui.py` 상단 상수(`COL_*`, `STATE_COLORS`)에 정의 — 색 추가/변경 시 여기만 수정.
