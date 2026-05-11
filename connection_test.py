# connection_test.py
# 실행: python connection_test.py

import ctypes
import socket
import subprocess
import platform
import sys
import os

MACHINE_IP = "192.168.10.108"
MACHINE_PORT = 8193
DLL_DIR  = r"C:\Users\MASTER\Desktop\DEV\Watcher\dll"
DLL_PATH = os.path.join(DLL_DIR, "Fwlib64.dll")



# ── 결과 출력 헬퍼 ──────────────────────────────────────────
def ok(msg):  print(f"  ✅ {msg}")
def fail(msg): print(f"  ❌ {msg}")
def warn(msg): print(f"  ⚠️  {msg}")
def section(title): print(f"\n{'─'*45}\n  {title}\n{'─'*45}")

# ══════════════════════════════════════════════
# STEP 1 : DLL 파일 존재 확인
# ══════════════════════════════════════════════
section("STEP 1 │ FOCAS DLL 파일 확인")

if not os.path.exists(DLL_PATH):
    fail(f"DLL을 찾을 수 없음: {DLL_PATH}")
    sys.exit(1)
ok(f"DLL 발견: {DLL_PATH}")

try:
    os.add_dll_directory(DLL_DIR)
    os.chdir(DLL_DIR)
    fanuc = ctypes.WinDLL(DLL_PATH)
    ok("DLL 로드 성공")
except OSError as e:
    fail(f"DLL 로드 실패: {e}")
    print("\n  힌트: 32bit DLL이면 32bit Python으로 실행하세요")
    print("        64bit DLL이면 64bit Python으로 실행하세요")
    sys.exit(1)

# ══════════════════════════════════════════════
# STEP 2 : 네트워크 PING 확인
# ══════════════════════════════════════════════
section("STEP 2 │ 네트워크 PING 테스트")

ping_param = "-n" if platform.system().lower() == "windows" else "-c"
ping_result = subprocess.run(
    ["ping", ping_param, "1", "-w", "2000", MACHINE_IP],
    capture_output=True
)
if ping_result.returncode == 0:
    ok(f"PING 성공 ({MACHINE_IP}) - 기계가 네트워크에 응답함")
else:
    fail(f"PING 실패 ({MACHINE_IP}) - 기계가 꺼져있거나 IP가 다를 수 있음")
    warn("IP를 다시 확인하세요. 계속 진행하지만 연결은 실패할 수 있습니다.")

# ══════════════════════════════════════════════
# STEP 3 : FOCAS 포트 열림 확인
# ══════════════════════════════════════════════
section("STEP 3 │ FOCAS 포트(8193) 확인")

try:
    with socket.create_connection((MACHINE_IP, MACHINE_PORT), timeout=3):
        ok(f"포트 {MACHINE_PORT} 열림 - FOCAS 통신 준비됨")
except (socket.timeout, ConnectionRefusedError, OSError) as e:
    fail(f"포트 {MACHINE_PORT} 닫힘 ({e})")
    warn("컨트롤러에서 FOCAS2 이더넷 기능이 비활성화되어 있을 수 있습니다.")
    warn("설정 경로: SYSTEM → 이더넷 파라미터 → FOCAS2 사용 = 1")

# ══════════════════════════════════════════════
# STEP 4 : FOCAS API로 실제 연결 시도
# ══════════════════════════════════════════════
section("STEP 4 │ FOCAS API 연결 시도 (핵심)")

# cnc_allclibhndl3: IP, Port, Timeout(초), &handle 반환
cnc_allclibhndl3 = fanuc.cnc_allclibhndl3
cnc_allclibhndl3.restype = ctypes.c_short

handle = ctypes.c_ushort()
TIMEOUT_SEC = 10

# 변경 후
ret = cnc_allclibhndl3(
    ctypes.c_char_p(MACHINE_IP.encode()),
    ctypes.c_ushort(MACHINE_PORT),
    ctypes.c_int(TIMEOUT_SEC),
    ctypes.byref(handle)
)

FOCAS_ERRORS = {
    0:   "EW_OK       - 정상 연결",
   -1:   "EW_BUSY     - 라이브러리 사용 중",
   -2:   "EW_NODLL    - DLL 없음",
   -3:   "EW_SOCKET   - 소켓 에러 (IP/포트 확인)",
   -4:   "EW_NOTOPEN  - 연결 실패 (기계 꺼짐 or IP 오류)",
   -8:   "EW_HANDLE   - 핸들 에러",
   -16:  "EW_REJECT   - 연결 거부 (라이선스/권한 문제)",
}

if ret == 0:
    ok(f"FOCAS 연결 성공! 핸들 번호: {handle.value}")

    # ── 연결 성공 시 기본 정보 조회 ──────────────
    section("STEP 5 │ 기본 정보 읽기 (연결 확인용)")

    # CNC 기종 정보 읽기
    class ODBSYS(ctypes.Structure):
        _fields_ = [
            ("addinfo",  ctypes.c_short),
            ("max_axis", ctypes.c_short),
            ("cnc_type", ctypes.c_char * 2),
            ("mt_type",  ctypes.c_char * 2),
            ("series",   ctypes.c_char * 4),
            ("version",  ctypes.c_char * 4),
            ("axes",     ctypes.c_char * 2),
        ]

    sys_info = ODBSYS()
    ret2 = fanuc.cnc_sysinfo(handle, ctypes.byref(sys_info))
    if ret2 == 0:
        ok(f"CNC 타입   : {sys_info.cnc_type.decode(errors='ignore').strip()}")
        ok(f"MT  타입   : {sys_info.mt_type.decode(errors='ignore').strip()}")
        ok(f"시리즈     : {sys_info.series.decode(errors='ignore').strip()}")
        ok(f"버전       : {sys_info.version.decode(errors='ignore').strip()}")
        ok(f"제어 축 수 : {sys_info.axes.decode(errors='ignore').strip()}")
    else:
        warn(f"기본 정보 읽기 실패 (ret={ret2}) - 연결 자체는 성공")

    # 연결 해제
    fanuc.cnc_freelibhndl(handle)
    ok("연결 정상 해제 완료")

else:
    err_msg = FOCAS_ERRORS.get(ret, f"알 수 없는 에러 코드: {ret}")
    fail(f"FOCAS 연결 실패 → {ret} : {err_msg}")

    if ret == -3:
        print("\n  ▶ 확인사항:")
        print("    1. 기계 IP가 맞는지 컨트롤러에서 재확인")
        print("    2. PC와 기계가 같은 서브넷인지 확인 (예: 둘 다 192.168.1.x)")
        print("    3. 방화벽에서 8193 포트 허용 여부")
    elif ret == -4:
        print("\n  ▶ 확인사항:")
        print("    1. 기계가 켜져 있는지 확인")
        print("    2. 컨트롤러 부팅이 완전히 끝났는지 확인")

# ══════════════════════════════════════════════
print(f"\n{'═'*45}")
print("  테스트 완료")
print(f"{'═'*45}\n")