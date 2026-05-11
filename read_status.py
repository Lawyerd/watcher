# read_status.py — FANUC 30i/31i 연결 테스트 스크립트
import ctypes
import os
import sys

# 🔴 수정 7: 하드코딩된 절대 경로 제거 → 스크립트 위치 기준 상대 경로 사용
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DLL_DIR      = os.path.join(BASE_DIR, "dll")
MACHINE_IP   = "192.168.10.108"
MACHINE_PORT = 8193

if not os.path.exists(DLL_DIR):
    print(f"❌ DLL 디렉토리를 찾을 수 없습니다: {DLL_DIR}")
    sys.exit(1)

os.add_dll_directory(DLL_DIR)
os.chdir(DLL_DIR)

dll_path = os.path.join(DLL_DIR, "Fwlib64.dll")
if not os.path.exists(dll_path):
    print(f"❌ Fwlib64.dll을 찾을 수 없습니다: {dll_path}")
    sys.exit(1)

fanuc = ctypes.WinDLL(dll_path)

# ── 연결 ──────────────────────────────────────────────────────
handle = ctypes.c_ushort()
fanuc.cnc_allclibhndl3.restype = ctypes.c_short
ret = fanuc.cnc_allclibhndl3(
    ctypes.c_char_p(MACHINE_IP.encode()),
    ctypes.c_ushort(MACHINE_PORT),
    ctypes.c_int(10),
    ctypes.byref(handle)
)
if ret != 0:
    print(f"❌ 연결 실패 (ret={ret})")
    sys.exit(1)
print(f"✅ 연결 성공\n")

# ── ODBST 구조체 ──────────────────────────────────────────────
class ODBST(ctypes.Structure):
    _fields_ = [
        ("dummy",     ctypes.c_short),
        ("tmmode",    ctypes.c_short),
        ("aut",       ctypes.c_short),
        ("run",       ctypes.c_short),
        ("motion",    ctypes.c_short),
        ("mstb",      ctypes.c_short),
        ("emergency", ctypes.c_short),
        ("alarm",     ctypes.c_short),
        ("edit",      ctypes.c_short),
    ]

stat = ODBST()
ret  = fanuc.cnc_statinfo(handle, ctypes.byref(stat))

if ret == 0:
    print("─── 운전 상태 (raw값) ───────────────────────")
    print(f"  dummy    : {stat.dummy}")
    print(f"  tmmode   : {stat.tmmode}")
    print(f"  aut      : {stat.aut}")
    print(f"  run      : {stat.run}")
    print(f"  motion   : {stat.motion}")
    print(f"  mstb     : {stat.mstb}")
    print(f"  emergency: {stat.emergency}")
    print(f"  alarm    : {stat.alarm}")
    print(f"  edit     : {stat.edit}")

    print("\n─── 운전 상태 (해석) ────────────────────────")
    aut_map = {0:"MDI", 1:"MEM(자동)", 3:"EDIT", 4:"HANDLE", 5:"JOG", 8:"INC", 9:"REF", 10:"REMOTE"}
    run_map = {0:"STOP", 1:"HOLD", 2:"RUN(자동운전중)", 3:"RUN(수동운전중)", 4:"RESTART"}
    print(f"  모드    : {aut_map.get(stat.aut, f'기타({stat.aut})')}")
    print(f"  상태    : {run_map.get(stat.run, f'기타({stat.run})')}")
    print(f"  비상정지: {'🚨 ON' if stat.emergency else '정상'}")
    print(f"  알람    : {'⚠️  있음' if stat.alarm else '정상'}")
else:
    print(f"❌ cnc_statinfo 실패 (ret={ret})")

fanuc.cnc_freelibhndl(handle)
print("\n✅ 연결 해제 완료")