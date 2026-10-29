"""[v3.1] 새 버전 확인·앱 안 업데이트 (회사 NAS).

build.ps1 -Publish가 설치 파일과 latest.json을 NAS(Z:\\VOL1\\releases\\watcher)에 올리면, 앱은 켤 때와 30분마다
사내 웹(LATEST_URL)을 읽어 지금보다 높은 버전이 있으면 화면(파란 띠)·트레이·토스트로 알린다.
[업데이트]를 누르면 설치 파일을 내려받아 해시를 확인하고, main이 화면 없이 설치(/VERYSILENT)를 띄운 뒤 종료한다.
설치 마법사는 앱이 정상 종료할 때까지 기다렸다가 설치하고 앱을 다시 켠다 (installer/CNC_Watcher.iss의 /UPDATE).

- 설치 마법사로 설치한 exe(옆에 unins*.exe)일 때만 확인한다. dist 빌드 폴더·python main.py는 확인하지 않는다.
- 장비 스레드와 별개 스레드 — 네트워크가 느리거나 사내망 밖이어도 FOCAS 읽기를 막지 않는다.
- 업데이트는 PC 화면(js_api)·트레이에서만 시작한다. 휴대폰(원격 서버)에서는 못 한다 (Funnel로 인터넷에 공개되므로).
- 파이썬이 내려받은 파일엔 '인터넷에서 받은 파일' 표시가 없어 'Windows의 PC 보호' 창이 뜨지 않는다.
"""
import os
import re
import sys
import glob
import json
import time
import shutil
import hashlib
import logging
import tempfile
import threading
import urllib.request
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

LATEST_URL = "http://192.168.0.220:8000/watcher/latest.json"
FIRST_CHECK_SEC = 20     # 켜자마자는 장비 연결이 먼저
CHECK_SEC = 30 * 60
TIMEOUT = 10
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "CNCWatcherUpdate")
# 사내 주소라 윈도우 프록시 설정을 타지 않게
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def parse_version(v):
    """'v3.1' → (3, 1). 형식이 틀리면 None"""
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", str(v or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def installed(base_dir):
    """설치 마법사로 설치한 exe인지 (옆에 제거 프로그램이 있다)"""
    return getattr(sys, "frozen", False) and bool(glob.glob(os.path.join(base_dir, "unins*.exe")))


class Updater(threading.Thread):
    """state: idle(새 버전 없음) / available / waiting(가공 끝나면) / queued / downloading / installing / error"""

    def __init__(self, version, enabled=True, url=LATEST_URL):
        super().__init__(daemon=True, name="updater")
        self.version, self.enabled, self.url = version, enabled, url
        self.info = None          # latest.json (지금보다 높은 버전일 때만)
        self.state, self.progress, self.error = "idle", 0, ""
        self.dismissed = None     # [나중에]를 누른 버전 — 다음에 켤 때까지 띠를 숨김
        self.open_request = False  # 트레이 '업데이트' → 화면이 업데이트 창을 연다
        self.busy = lambda: []    # 프로그램이 끝나지 않은 장비 이름 (main이 poller.busy_names로 바꿈)
        self.on_found = None      # 새 버전을 처음 찾았을 때 (토스트·트레이 메뉴)
        self.on_ready = None      # 설치 파일 준비 끝 → main이 설치를 띄우고 종료
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._last_fail = None

    # ── 화면(js_api)·트레이에서 부르는 것 ─────────────────────
    def public(self):
        """화면에 줄 상태 (새 버전이 없으면 None)"""
        info = self.info
        if not info:
            return None
        opened, self.open_request = self.open_request, False
        return {"state": self.state, "version": info["version"], "current": self.version, "notes": info["notes"],
                "size": info.get("size") or 0, "date": info.get("date") or "", "progress": self.progress,
                "error": self.error, "dismissed": self.dismissed == info["version"], "busy": self.busy(), "open": opened}

    def request(self, now):
        """업데이트 시작. now=False면 가공 중인 장비가 있을 때 끝날 때까지 기다린다"""
        with self._lock:
            if self.info and self.state in ("available", "waiting", "error"):
                self.state = "waiting" if not now and self.busy() else "queued"
                self.error = ""
                logger.info(f"업데이트 {self.info['version']} {'가공 끝나면' if self.state == 'waiting' else '지금'} 시작")
        self._wake.set()
        return self.state

    def cancel(self):
        with self._lock:
            if self.state == "waiting":
                self.state = "available"
                logger.info("가공 끝나면 업데이트 취소")

    def dismiss(self):
        if self.info:
            self.dismissed = self.info["version"]

    # ── 확인·내려받기 (이 스레드) ─────────────────────────────
    def run(self):
        if not self.enabled:
            return
        shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)   # 지난 업데이트 때 받은 설치 파일
        next_check = time.time() + FIRST_CHECK_SEC
        while True:
            if self.state == "queued" or (self.state == "waiting" and not self.busy()):
                self._download()
            elif self.state in ("idle", "available", "error") and time.time() >= next_check:
                self.check()
                next_check = time.time() + CHECK_SEC
            self._wake.wait(5)
            self._wake.clear()

    def check(self):
        try:
            with _opener.open(self.url, timeout=TIMEOUT) as r:
                info = json.loads(r.read(64 * 1024).decode("utf-8-sig"))
        except (OSError, ValueError) as e:
            if str(e) != self._last_fail:   # 사내망 밖 PC면 30분마다 실패하므로 같은 오류는 한 번만
                self._last_fail = str(e)
                logger.info(f"새 버전 확인 실패: {e}")
            return
        self._last_fail = None
        new, cur = parse_version(info.get("version")), parse_version(self.version)
        name = str(info.get("file") or "")
        if not (new and cur and new > cur and re.fullmatch(r"[\w.\-]+\.exe", name) and info.get("sha256")):
            return
        notes = info.get("notes") or []
        info["notes"] = [str(n) for n in (notes if isinstance(notes, list) else [notes]) if str(n).strip()]
        first = not self.info or self.info["version"] != info["version"]
        with self._lock:
            self.info = info
            if self.state in ("idle", "error"):
                self.state = "available"
        if first:
            logger.info(f"새 버전 {info['version']} 발견 (지금 {self.version})")
            if self.on_found:
                self.on_found(info)

    def _download(self):
        info = self.info
        with self._lock:
            self.state, self.progress, self.error = "downloading", 0, ""
        url = urljoin(self.url, info["file"])
        path = os.path.join(DOWNLOAD_DIR, info["file"])
        part = path + ".part"
        try:
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            h, got = hashlib.sha256(), 0
            with _opener.open(url, timeout=TIMEOUT) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length") or info.get("size") or 0)
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    got += len(chunk)
                    if total:
                        self.progress = min(99, got * 100 // total)
            if h.hexdigest().lower() != str(info["sha256"]).lower():
                raise ValueError("내려받은 파일이 NAS의 원본과 다릅니다 (해시 불일치)")
            os.replace(part, path)
        except (OSError, ValueError) as e:
            logger.error(f"업데이트 내려받기 실패: {e}")
            try:
                os.remove(part)
            except OSError:
                pass
            with self._lock:
                self.state = "error"
                self.error = str(e) if isinstance(e, ValueError) else "NAS에서 설치 파일을 받지 못했습니다"
            return
        self.progress = 100
        self.state = "installing"
        logger.info(f"업데이트 {info['version']} 내려받기 끝 ({got:,}B) → 설치 시작")
        if self.on_ready:
            self.on_ready(path)
