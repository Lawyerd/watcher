# read_status.py
import ctypes, os

DLL_DIR      = r"C:\Users\MASTER\Desktop\DEV\Watcher\dll"
MACHINE_IP   = "192.168.10.108"
MACHINE_PORT = 8193

os.add_dll_directory(DLL_DIR)
os.chdir(DLL_DIR)
fanuc = ctypes.WinDLL(os.path.join(DLL_DIR, "Fwlib64.dll"))

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
    exit()
print(f"✅ 연결 성공\n")

# 30i/31i용 ODBST (fwlib.cs WIN64 버전 기준)
class ODBST(ctypes.Structure):
    _fields_ = [
        ("dummy",     ctypes.c_short),  # short 1개 (WIN64 버전)
        ("tmmode",    ctypes.c_short),  # T/M mode
        ("aut",       ctypes.c_short),  # 자동 모드
        ("run",       ctypes.c_short),  # 운전 상태
        ("motion",    ctypes.c_short),  # 축이동/드웰
        ("mstb",      ctypes.c_short),  # M/S/T/B
        ("emergency", ctypes.c_short),  # 비상정지
        ("alarm",     ctypes.c_short),  # 알람
        ("edit",      ctypes.c_short),  # 편집 상태
    ]

stat = ODBST()
ret = fanuc.cnc_statinfo(handle, ctypes.byref(stat))
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
    run_map = {0:"STOP", 1:"HOLD", 2:"START(자동운전중)", 3:"MSTR(수동운전중)", 4:"RESTART"}
    print(f"  모드    : {aut_map.get(stat.aut, f'기타({stat.aut})')}")
    print(f"  상태    : {run_map.get(stat.run, f'기타({stat.run})')}")
    print(f"  비상정지: {'🚨 ON' if stat.emergency else '정상'}")
    print(f"  알람    : {'⚠️  있음' if stat.alarm else '정상'}")
else:
    print(f"❌ cnc_statinfo 실패 (ret={ret})")

fanuc.cnc_freelibhndl(handle)
print("\n✅ 연결 해제 완료")