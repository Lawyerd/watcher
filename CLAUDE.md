# CNC Watcher

FANUC CNC 장비(DN Solutions DVF5000/DVF6500)를 FOCAS 라이브러리로 실시간 모니터링하는 Windows 데스크톱 앱.
현재 버전 **v2.3** (2026-08-03 배포). Python + customtkinter, PyInstaller로 exe 배포.

## 파일 구조

| 파일 | 역할 |
|---|---|
| `main.py` | 진입점 + MainController. 폴링 루프(보임 0.5s / 숨김 3s), 자동 재연결, 트레이, 설정 저장, 아이콘 생성 |
| `fanuc_logic.py` | FOCAS 통신 (`FanucMachine`). 상태/사이클타임(파라미터 6757·6758)/공구번호(매크로 4120) 읽기 |
| `monitor_ui.py` | UI 전부 (`AppUI`, `SettingsDialog`, 다크 테마 팔레트). 상태 반영은 `AppUI.apply_status()` 한 곳으로 일원화 |
| `notifier.py` | 상태 전이 감지 → winotify 토스트 + `logs/history_YYYY-MM-DD.csv` 가공 이력 기록 |
| `machines.json` | 장비 목록 (앱 내 ⚙️ 설정 UI로 편집 가능, 재시작 불필요) |
| `read_status.py`, `connection_test.py` | 단독 연결 테스트 스크립트 |

## 반드시 알아야 할 제약 (고생해서 알아낸 것들)

1. **FOCAS 핸들은 만든 스레드에서만 유효.** 다른 스레드에서 쓰면 EW_HANDLE(-8).
   → 자동 재연결은 백그라운드 스레드에서 TCP 프로브만 하고, 실제 `cnc_allclibhndl3`는 `app.after(0, ...)`로 메인 스레드에서 실행 (`main.py try_reconnect/_finish_reconnect`). 절대 백그라운드에서 FOCAS 함수를 호출하지 말 것.
2. **절전 복귀 시 FOCAS 함수가 음수 오류(-16 EW_SOCKET 등)를 반환** → `fetch_data`에서 ret != 0이면 `drop_connection()` 후 자동 재연결에 맡김. 오류를 무시하면 화면이 옛날 값으로 멈춘다.
3. **plyer 토스트는 Win11에서 오류 없이 무시됨.** winotify(네이티브 토스트) 사용, plyer는 폴백. 토스트 아이콘은 256px PNG 필요 (`icons/watcher_icon.png`).
4. **CTkFrame 기본 크기가 200×200.** 얇은 스트립 등을 만들 때 `height=10` 같은 최소값을 명시하지 않으면 레이아웃이 부푼다.
5. **customtkinter는 Toplevel 생성 200ms 후 기본 아이콘으로 덮어씀** → `after(250, lambda: win.iconbitmap(...))`로 재적용 (SettingsDialog, 알람 팝업).
6. **JetBrains Mono는 fonts/ 폴더로 동봉 배포** — `AddFontResourceEx(FR_PRIVATE)`로 프로세스 전용 로드(`load_private_fonts()`), 시스템 설치 불필요. 폰트 폴백: JetBrains Mono → Cascadia Mono → Consolas. OFL.txt 라이선스 파일 필수 동봉.
7. **최소화(슬림) 모드 창 높이는 계산식이 아니라 실측** — `update_idletasks()` 후 `scroll.winfo_reqheight()` 사용.
8. 알림 토글(🔕)은 토스트만 끈다. **CSV 가공 이력은 항상 기록**. OFFLINE 전이는 가공 이벤트로 취급하지 않음 (가짜 '가공 완료' 방지).
9. 중복 실행 방지: 127.0.0.1:54321 포트 바인딩.

## 빌드 & 배포

```bash
pyinstaller CNC_Watcher_v2.3.spec --noconfirm && cp -r dll icons fonts dist/CNC_Watcher_v2.3/ && cp machines.json dist/CNC_Watcher_v2.3/
```

- **재빌드하면 dist 폴더가 초기화되므로 dll/icons/fonts/machines.json 복사를 매번 다시 해야 한다.**
- 빌드 전 실행 중인 exe를 종료할 것 (dll 잠김으로 빌드 실패).
- `dist\CNC_Watcher_v2.3\` 폴더 전체가 완전한 배포본 — 공장 PC에 폴더째 복사하면 끝.
- `*.spec`은 gitignore 대상(로컬 전용). 버전 올릴 때 spec 복사 후 name/icon 수정.
- 창 제목 버전(`monitor_ui.py`의 `self.title(...)`)도 같이 올릴 것.

## 테스트 방법

- UI 검증: 가짜 머신 객체로 `AppUI`를 띄우고 `apply_status()` 호출 → PIL `ImageGrab`으로 스크린샷 (실제 장비 불필요).
- FOCAS 검증: 개발 PC에서 실장비(192.168.10.109/108, 포트 8193) 직접 접근 가능. `read_status.py` 참고.
- 실장비 연결 검증(절전 복귀, 가공 완료 알림 등)은 사용자만 가능 — 수정 후 사용자 확인을 기다릴 것.

## 컨벤션

- 소통·주석·커밋 메시지 한국어. 커밋은 이모지 접두사: `🎨 design:` `🐛 fix:` `🔧 feature/chore:` `📦 feature:`
- UI 변경은 코드보다 **목업 시안(2~4개)을 먼저** 보여주고 사용자가 고른 뒤 구현. 구현 후 스크린샷으로 확인시키고, 사용자가 "커밋해줘" 하면 커밋·푸시.
- 다크 테마 색상 팔레트는 `monitor_ui.py` 상단 상수(`COL_*`, `STATE_COLORS`)에 정의 — 색 추가/변경 시 여기만 수정.
