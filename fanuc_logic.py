import ctypes
import datetime

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

# PMC 영역 읽기용 구조체 (pmc_rdpmcrng, word 단위)
class IODBPMC(ctypes.Structure):
    _fields_ = [
        ("type_a",   ctypes.c_short), ("type_d",   ctypes.c_short),
        ("datano_s", ctypes.c_short), ("datano_e", ctypes.c_short),
        ("idata",    ctypes.c_short * 5),
    ]

# [v2.4] DN Solutions PMC 공구 레지스터 (DVF5000/DVF6500 실측)
#   D0450 = 스핀들에 장착된 현재 공구, D0452 = 대기(다음) 공구
#   매크로 #4120은 '마지막 지령 T코드'라서 T 선지령 시 대기 공구가 나온다.
PMC_D = 9
PMC_TOOL_ADDR = 450

# [v2.4] 현재 알람 메시지 (cnc_rdalmmsg2)
class ODBALMMSG2(ctypes.Structure):
    _fields_ = [
        ("alm_no",  ctypes.c_int),   ("type",    ctypes.c_short),
        ("axis",    ctypes.c_short), ("dummy",   ctypes.c_short),
        ("msg_len", ctypes.c_short), ("alm_msg", ctypes.c_char * 64),
    ]

MAX_ALARMS = 10
# 30i/31i 알람 종류 → 화면에 표시되는 접두어 (예: SV0401, EX1012)
ALARM_PREFIX = {0: "SW", 1: "PW", 2: "IO", 3: "PS", 4: "OT", 5: "OH", 6: "SV", 7: "SR",
                8: "MC", 9: "SP", 10: "DS", 11: "IE", 12: "BG", 13: "SN", 15: "EX", 19: "PC"}

# [v2.4] 부하 미터 (cnc_rdspmeter 스핀들 / cnc_rdsvmeter 서보축)
class LOADELM(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_int), ("dec", ctypes.c_short), ("unit", ctypes.c_short),
        ("name", ctypes.c_char), ("suff1", ctypes.c_char), ("suff2", ctypes.c_char), ("reserve", ctypes.c_char),
    ]

class ODBSPLOAD(ctypes.Structure):
    _fields_ = [("spload", LOADELM), ("spspeed", LOADELM)]

class ODBACT(ctypes.Structure):
    _fields_ = [("dummy", ctypes.c_short * 2), ("data", ctypes.c_int)]

# [v2.4] 실행 중인 프로그램 (cnc_exeprgname: O번호 또는 파일명, 예 "O1234" / "1011-2.nc")
class ODBEXEPRG(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char * 36), ("o_num", ctypes.c_int)]

MAX_AXES = 8

def _meter(e):
    return round(e.data / (10 ** e.dec) if e.dec > 0 else e.data)

def _axis_name(e):
    """축 이름 (X, Y, Z, A, B, C …). 빈 칸(\\x00)이면 None — 기계마다 축 구성이 달라 빈 슬롯이 섞여 온다"""
    name = e.name.decode("ascii", "ignore").strip("\x00 ")
    if not name:
        return None
    suff = e.suff1.decode("ascii", "ignore").strip("\x00 ")
    return name + suff if suff.isalnum() else name

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
            "cycle_time": "00:00:00", "tool": "T--", "next_tool": "T--", "is_alarm": False,
            "alarms": [],  # [{"code": "SV0401", "msg": "...", "since": "HH:MM:SS"}]
            "spindle_load": None, "spindle_rpm": None,   # [v2.4] 스핀들 부하(%)·실제 회전수
            "axis_loads": [],                            # [("X", 12), ("Y", 9), …] 기계에 있는 축만
            "program": None,                             # [v2.4] 실행 중인 프로그램명 (없으면 None)
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
            self.data["alarms"] = []

    def drop_connection(self):
        """통신 오류(절전 복귀 등) 시 죽은 핸들을 정리하고 오프라인 처리"""
        try:
            self.fanuc.cnc_freelibhndl(self.handle)
        except Exception:
            pass
        self.is_connected = False
        self.data["status"] = "OFFLINE"
        self.data["alarms"] = []

    def read_alarms(self):
        """현재 발생 중인 알람 목록. 발생 시각은 FOCAS가 주지 않으므로 처음 본 시각을 유지한다."""
        buf = (ODBALMMSG2 * MAX_ALARMS)()
        num = ctypes.c_short(MAX_ALARMS)
        if self.fanuc.cnc_rdalmmsg2(self.handle, ctypes.c_short(-1), ctypes.byref(num), buf) != 0:
            return self.data["alarms"]   # 읽기 실패 시 이전 목록 유지

        since = {a["code"]: a["since"] for a in self.data["alarms"]}
        now = datetime.datetime.now().strftime("%H:%M:%S")
        alarms = []
        for a in buf[:max(0, min(num.value, MAX_ALARMS))]:
            prefix = ALARM_PREFIX.get(a.type, f"T{a.type}-")
            code = f"{prefix}{a.alm_no:04d}"
            # 한글 화면 설정이면 KS 완성형(cp949)으로 내려옴. 영문은 ASCII라 그대로 디코딩됨
            msg = a.alm_msg[:max(0, a.msg_len)].decode("cp949", "replace").strip()
            alarms.append({"code": code, "msg": msg, "since": since.get(code, now)})
        return alarms

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
        # [v2.4] 알람 내용은 알람 상태일 때만 읽음 (평상시 통신량 증가 없음)
        self.data["alarms"] = self.read_alarms() if stat.alarm else []

        # 2. 사이클 타임 (가공 시간)
        prm_min, prm_msec = IODBPRM(), IODBPRM()
        res_min = self.fanuc.cnc_rdparam(self.handle, ctypes.c_short(6758), ctypes.c_short(0), ctypes.c_short(8), ctypes.byref(prm_min))
        res_msec = self.fanuc.cnc_rdparam(self.handle, ctypes.c_short(6757), ctypes.c_short(0), ctypes.c_short(8), ctypes.byref(prm_msec))
        if res_min == 0 and res_msec == 0:
            total_sec = (prm_min.prm_val * 60) + (prm_msec.prm_val // 1000)
            hh, mm = divmod(total_sec, 3600)
            mm, ss = divmod(mm, 60)
            self.data["cycle_time"] = f"{hh:02d}:{mm:02d}:{ss:02d}"

        # 3. [v2.4 수정] 스핀들 공구 / 대기 공구 (PMC D0450~D0453, word 2개)
        pmc = IODBPMC()
        if self.fanuc.pmc_rdpmcrng(self.handle, ctypes.c_short(PMC_D), ctypes.c_short(1),
                                   ctypes.c_ushort(PMC_TOOL_ADDR), ctypes.c_ushort(PMC_TOOL_ADDR + 3),
                                   ctypes.c_ushort(8 + 2 * 2), ctypes.byref(pmc)) == 0:
            spindle, nxt = pmc.idata[0], pmc.idata[1]
            self.data["tool"] = f"T{spindle:02d}" if spindle > 0 else "T00"
            self.data["next_tool"] = f"T{nxt:02d}" if nxt > 0 else "T00"

        # 4. [v2.4] 스핀들·축 부하 (축 구성은 기계마다 다름: XYZ / XYZBC / XYZAC …)
        sp = (ODBSPLOAD * 2)()
        n = ctypes.c_short(2)
        if self.fanuc.cnc_rdspmeter(self.handle, ctypes.c_short(-1), ctypes.byref(n), sp) == 0 and n.value > 0:
            self.data["spindle_load"] = _meter(sp[0].spload)
        act = ODBACT()
        if self.fanuc.cnc_acts(self.handle, ctypes.byref(act)) == 0:
            self.data["spindle_rpm"] = act.data
        sv = (LOADELM * MAX_AXES)()
        n = ctypes.c_short(MAX_AXES)
        if self.fanuc.cnc_rdsvmeter(self.handle, ctypes.byref(n), sv) == 0:
            self.data["axis_loads"] = [(_axis_name(a), _meter(a)) for a in sv[:max(0, min(n.value, MAX_AXES))]
                                       if _axis_name(a)]

        # 5. [v2.4] 실행 중인 프로그램 — 선택된 프로그램이 없으면 "O0"으로 오므로 None 처리
        prg = ODBEXEPRG()
        if self.fanuc.cnc_exeprgname(self.handle, ctypes.byref(prg)) == 0:
            name = prg.name.decode("cp949", "replace").strip("\x00 ")
            self.data["program"] = None if name in ("", "O0", "O0000") else name