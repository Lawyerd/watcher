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

# ── IODBPMC 구조체 (PMC 영역 읽기용, word 단위) ─────────────────
class IODBPMC(ctypes.Structure):
    _fields_ = [
        ("type_a",   ctypes.c_short),
        ("type_d",   ctypes.c_short),
        ("datano_s", ctypes.c_short),
        ("datano_e", ctypes.c_short),
        ("idata",    ctypes.c_short * 5),
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

# ── 공구 번호 (PMC D0450 스핀들 / D0452 대기) ─────────────────
print("\n─── 공구 정보 읽기 ──────────────────────────")
# 매크로 #4120은 '마지막으로 지령된 T코드'라서 T 선지령 시 대기 공구가 나옴
# → DN Solutions PMC 레지스터에서 직접 읽음 (adr_type 9 = D, data_type 1 = word)
pmc = IODBPMC()
ret_pmc = fanuc.pmc_rdpmcrng(handle, ctypes.c_short(9), ctypes.c_short(1),
                             ctypes.c_ushort(450), ctypes.c_ushort(453),
                             ctypes.c_ushort(12), ctypes.byref(pmc))

if ret_pmc == 0:
    print(f"  현재 공구 : T{pmc.idata[0]:02d}")
    print(f"  대기 공구 : T{pmc.idata[1]:02d}")
else:
    print(f"❌ 공구 번호 읽기 실패 (ret={ret_pmc})")

fanuc.cnc_freelibhndl(handle)
print("\n✅ 연결 해제 완료")