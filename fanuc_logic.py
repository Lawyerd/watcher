import ctypes

class ODBST(ctypes.Structure):
    _fields_ = [
        ("dummy", ctypes.c_short), ("tmmode", ctypes.c_short),
        ("aut", ctypes.c_short), ("run", ctypes.c_short),
        ("motion", ctypes.c_short), ("mstb", ctypes.c_short),
        ("emergency", ctypes.c_short), ("alarm", ctypes.c_short),
        ("edit", ctypes.c_short),
    ]

class IODBPRM(ctypes.Structure):
    _fields_ = [
        ("datano", ctypes.c_short), ("type", ctypes.c_short),
        ("prm_val", ctypes.c_int), ("dummy", ctypes.c_int),
    ]

# [추가] 공구 번호를 정확히 읽기 위한 매크로 구조체 (C언어 메모리 정렬 맞춤)
class ODBMACRO(ctypes.Structure):
    _pack_ = 2  
    _fields_ = [
        ("datano",  ctypes.c_short),
        ("dummy",   ctypes.c_short),
        ("mcr_val", ctypes.c_int),
        ("dec_val", ctypes.c_short),
    ]

class FanucMachine:
    def __init__(self, name, ip, port=8193, dll_path=""):
        self.name = name
        self.ip = ip
        self.port = port
        self.handle = ctypes.c_ushort()
        self.is_connected = False
        self.want_connected = False   # 사용자가 연결을 원하는 상태 (자동 재연결 기준)
        self.fanuc = ctypes.WinDLL(dll_path) if dll_path else None
        
        self.data = {
            "mode": "-", "status": "OFFLINE", 
            "cycle_time": "00:00:00", "tool": "T--", "is_alarm": False
        }

    def connect(self):
        if not self.fanuc: return False
        ret = self.fanuc.cnc_allclibhndl3(
            ctypes.c_char_p(self.ip.encode()), 
            ctypes.c_ushort(self.port), 
            ctypes.c_int(3), 
            ctypes.byref(self.handle)
        )
        if ret == 0:
            self.is_connected = True
            return True
        return False

    def disconnect(self):
        if self.is_connected:
            self.fanuc.cnc_freelibhndl(self.handle)
            self.is_connected = False
            self.data["status"] = "OFFLINE"

    def drop_connection(self):
        """통신 오류(절전 복귀 등) 시 죽은 핸들을 정리하고 오프라인 처리"""
        try:
            self.fanuc.cnc_freelibhndl(self.handle)
        except Exception:
            pass
        self.is_connected = False
        self.data["status"] = "OFFLINE"

    def fetch_data(self):
        if not self.is_connected: return

        # 1. 운전 상태 및 알람 체크
        stat = ODBST()
        ret = self.fanuc.cnc_statinfo(self.handle, ctypes.byref(stat))
        if ret != 0:
            # 절전 복귀 후 소켓이 죽으면 EW_SOCKET(-16) 등 오류 코드 반환
            # → 핸들을 버리고 끊김 처리 (재연결은 main 루프가 자동 수행)
            self.drop_connection()
            return
        aut_map = {0:"MDI", 1:"MEM", 2:"EDIT", 3:"EDIT", 4:"HNDL", 5:"JOG", 9:"REF", 10:"RMT"}
        run_map = {0:"STOP", 1:"IDLE", 2:"HOLD(M00)", 3:"RUN", 4:"WARMUP"}
        self.data["mode"] = aut_map.get(stat.aut, f"E({stat.aut})")
        self.data["status"] = run_map.get(stat.run, f"CODE({stat.run})")
        self.data["is_alarm"] = bool(stat.alarm)

        # 2. 사이클 타임 (가공 시간)
        prm_min, prm_msec = IODBPRM(), IODBPRM()
        res_min = self.fanuc.cnc_rdparam(self.handle, ctypes.c_short(6758), ctypes.c_short(0), ctypes.c_short(8), ctypes.byref(prm_min))
        res_msec = self.fanuc.cnc_rdparam(self.handle, ctypes.c_short(6757), ctypes.c_short(0), ctypes.c_short(8), ctypes.byref(prm_msec))
        if res_min == 0 and res_msec == 0:
            total_sec = (prm_min.prm_val * 60) + (prm_msec.prm_val // 1000)
            hh, mm = divmod(total_sec, 3600)
            mm, ss = divmod(mm, 60)
            self.data["cycle_time"] = f"{hh:02d}:{mm:02d}:{ss:02d}"

        # 3. [수정] 실제 공구 번호 읽기 (매크로 4120번)
        macro = ODBMACRO()
        if self.fanuc.cnc_rdmacro(self.handle, ctypes.c_short(4120), ctypes.c_short(10), ctypes.byref(macro)) == 0:
            t_code = macro.mcr_val
            if macro.dec_val > 0:
                t_code = int(t_code / (10 ** macro.dec_val))
            
            self.data["tool"] = f"T{t_code:02d}" if t_code > 0 else "T00"