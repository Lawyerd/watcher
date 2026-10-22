"""[v3.0] 윈도우 시작 시 자동 실행 — HKCU\\...\\Run 레지스트리 값 하나로 켜고 끈다.
관리자 권한이 필요 없고, 이 사용자가 로그인할 때 실행된다 (로그인 전 부팅 단계에서는 안 뜸).
'트레이로 숨겨서 시작'은 등록 명령의 --tray 인자로 기억하므로 별도 설정 파일이 없다."""
import sys
import logging
import winreg

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "CNC Watcher"
TRAY_ARG = "--tray"


def available():
    """exe로 실행할 때만 (python main.py는 실행 경로가 고정돼 있지 않음)"""
    return bool(getattr(sys, "frozen", False))


def _command(tray):
    return f'"{sys.executable}"' + (f" {TRAY_ARG}" if tray else "")


def read():
    """(켜짐 여부, 트레이로 시작 여부, 등록된 명령). 꺼져 있으면 트레이 시작을 기본값으로"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            cmd = str(winreg.QueryValueEx(k, VALUE)[0])
    except OSError:
        return False, True, None
    return True, TRAY_ARG in cmd, cmd


def write(on, tray=True):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, VALUE, 0, winreg.REG_SZ, _command(tray))
        else:
            try:
                winreg.DeleteValue(k, VALUE)
            except FileNotFoundError:
                pass
    logger.info(f"자동 실행 {'켜짐' + (' (트레이로 시작)' if tray else '') if on else '꺼짐'}")


def follow_current_exe():
    """켜져 있는데 다른 exe(이전 버전 폴더 등)를 가리키면 지금 실행한 exe로 바꾼다.
    버전마다 dist 폴더가 달라서, 그대로 두면 예전 빌드가 자동 실행된다."""
    on, tray, cmd = read()
    if on and available() and cmd != _command(tray):
        write(True, tray)
        logger.info(f"자동 실행 경로 갱신: {cmd} → {_command(tray)}")
