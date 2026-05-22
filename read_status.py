# read_status.py — FANUC 30i/31i 연결 테스트 스크립트
import ctypes
import os
import sys

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

# ── ODBST 구조체 (운전 상태) ──────────────────────────────────
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

# ── ODBMACRO 구조체 (공구 번호 읽기용) ──────────────────────────
class ODBMACRO(ctypes.Structure):
    _pack_ = 2  # FOCAS C언어 구조체 크기(10바이트)와 완벽히 맞추기 위한 필수 옵션
    _fields_ = [
        ("datano",  ctypes.c_short),
        ("dummy",   ctypes.c_short),
        ("mcr_val", ctypes.c_int),    # 실제 공구 번호가 들어가는 곳
        ("dec_val", ctypes.c_short),
    ]

stat = ODBST()
ret  = fanuc.cnc_statinfo(handle, ctypes.byref(stat))

if ret == 0:
    print("─── 운전 상태 (해석) ────────────────────────")
    aut_map = {0:"MDI", 1:"MEM(자동)", 3:"EDIT", 4:"HANDLE", 5:"JOG", 8:"INC", 9:"REF", 10:"REMOTE"}
    run_map = {0:"STOP", 1:"HOLD", 2:"RUN(자동운전중)", 3:"RUN(수동운전중)", 4:"RESTART"}
    print(f"  모드    : {aut_map.get(stat.aut, f'기타({stat.aut})')}")
    print(f"  상태    : {run_map.get(stat.run, f'기타({stat.run})')}")
    print(f"  비상정지: {'🚨 ON' if stat.emergency else '정상'}")
    print(f"  알람    : {'⚠️  있음' if stat.alarm else '정상'}")
else:
    print(f"❌ cnc_statinfo 실패 (ret={ret})")

# ── 공구 번호 (매크로 4120번 읽기) ────────────────────────────
print("\n─── 공구 정보 읽기 ──────────────────────────")
macro = ODBMACRO()
# 4120번 매크로 = FANUC 표준 '마지막으로 지령된 T코드'
ret_macro = fanuc.cnc_rdmacro(handle, ctypes.c_short(4120), ctypes.c_short(10), ctypes.byref(macro))

if ret_macro == 0:
    real_tool = macro.mcr_val
    # 소수점 처리 방어 로직 (보통 T코드는 소수점이 없으나 안전을 위해 추가)
    if macro.dec_val > 0:
        real_tool = int(real_tool / (10 ** macro.dec_val))
        
    print(f"  현재 공구 : T{real_tool:02d}")
else:
    print(f"❌ 공구 번호 읽기 실패 (ret={ret_macro})")

fanuc.cnc_freelibhndl(handle)
print("\n✅ 연결 해제 완료")