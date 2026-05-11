import ctypes
import logging

logger = logging.getLogger(__name__)

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

class IODBPRM(ctypes.Structure):
    _fields_ = [
        ("datano",  ctypes.c_short),
        ("type",    ctypes.c_short),
        ("prm_val", ctypes.c_int),
        ("dummy",   ctypes.c_int),
    ]

class ODBMDL(ctypes.Structure):
    _fields_ = [
        ("dummy", ctypes.c_short * 2),
        ("modal", ctypes.c_int * 32),
    ]

class FanucMachine:
    # 🔴 수정 1: run_map을 실제 FANUC 30i/31i 스펙에 맞게 수정
    # 기존: {0:"STOP", 1:"IDLE", 2:"HOLD(M00)", 3:"RUN", 4:"WARMUP"}
    # → notifier의 "RUN" in status 조건이 절대 참이 되지 않았음
    RUN_MAP = {
        0: "STOP",
        1: "HOLD",
        2: "RUN",      # START (자동운전중) → "RUN" 포함으로 notifier 정상 작동
        3: "RUN(M)",   # MSTR (수동운전중) → "RUN" 포함
        4: "RESTART",
    }
    AUT_MAP = {
        0: "MDI",
        1: "MEM",
        3: "EDIT",
        4: "HNDL",
        5: "JOG",
        8: "INC",
        9: "REF",
        10: "RMT",
    }

    def __init__(self, name, ip, port=8193, dll_path=""):
        self.name = name
        self.ip = ip
        self.port = port
        self.handle = ctypes.c_ushort()
        self.is_connected = False
        self.fanuc = ctypes.WinDLL(dll_path) if dll_path else None

        self.data = {
            "mode":       "-",
            "status":     "OFFLINE",
            "cycle_time": "00:00:00",
            "tool":       "T--",
            "is_alarm":   False,
        }

    def connect(self):
        if not self.fanuc:
            logger.warning(f"[{self.name}] DLL이 로드되지 않았습니다.")
            return False
        ret = self.fanuc.cnc_allclibhndl3(
            ctypes.c_char_p(self.ip.encode()),
            ctypes.c_ushort(self.port),
            ctypes.c_int(3),
            ctypes.byref(self.handle)
        )
        if ret == 0:
            self.is_connected = True
            logger.info(f"[{self.name}] 연결 성공")
            return True
        logger.warning(f"[{self.name}] 연결 실패 (ret={ret})")
        return False

    def disconnect(self):
        if self.is_connected:
            self.fanuc.cnc_freelibhndl(self.handle)
            self.is_connected = False
            self.data["status"] = "OFFLINE"
            logger.info(f"[{self.name}] 연결 해제")

    def fetch_data(self):
        if not self.is_connected:
            return

        # ── 운전 상태 ──────────────────────────────────────────
        stat = ODBST()
        ret = self.fanuc.cnc_statinfo(self.handle, ctypes.byref(stat))
        if ret == 0:
            self.data["mode"]     = self.AUT_MAP.get(stat.aut, f"E({stat.aut})")
            self.data["status"]   = self.RUN_MAP.get(stat.run, f"CODE({stat.run})")
            self.data["is_alarm"] = bool(stat.alarm)
        else:
            logger.debug(f"[{self.name}] cnc_statinfo 실패 (ret={ret})")

        # ── 사이클 타임 ────────────────────────────────────────
        prm_min  = IODBPRM()
        prm_msec = IODBPRM()
        res_min  = self.fanuc.cnc_rdparam(
            self.handle, ctypes.c_short(6758), ctypes.c_short(0),
            ctypes.c_short(8), ctypes.byref(prm_min)
        )
        res_msec = self.fanuc.cnc_rdparam(
            self.handle, ctypes.c_short(6757), ctypes.c_short(0),
            ctypes.c_short(8), ctypes.byref(prm_msec)
        )
        if res_min == 0 and res_msec == 0:
            total_sec = (prm_min.prm_val * 60) + (prm_msec.prm_val // 1000)
            hh, rem   = divmod(total_sec, 3600)
            mm, ss    = divmod(rem, 60)
            self.data["cycle_time"] = f"{hh:02d}:{mm:02d}:{ss:02d}"
        else:
            logger.debug(f"[{self.name}] cnc_rdparam 실패 (min={res_min}, msec={res_msec})")

        # ── 공구 번호 ──────────────────────────────────────────
        # 🔴 수정 2: cnc_modal 첫 번째 데이터 번호를 -3(현재 T코드)으로 변경
        # 기존 108번은 비표준이었음
        modal = ODBMDL()
        ret_modal = self.fanuc.cnc_modal(
            self.handle, ctypes.c_short(-3), ctypes.c_short(0),
            ctypes.byref(modal)
        )
        if ret_modal == 0:
            t_code = modal.modal[0]
            self.data["tool"] = f"T{t_code:02d}" if t_code >= 0 else "T--"
        else:
            logger.debug(f"[{self.name}] cnc_modal 실패 (ret={ret_modal})")