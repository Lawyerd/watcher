"""설치 마법사 그림 — icons/watcher_icon.png로 환영·완료 화면 왼쪽 큰 그림(164×314)과
나머지 화면 오른쪽 위 작은 그림(55×55)을 100%·200% 화면 배율용으로 만든다. build.ps1이 호출."""
import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "build", "installer")
icon = Image.open(os.path.join(ROOT, "icons", "watcher_icon.png")).convert("RGBA")


def make(name, w, h, icon_px, bg):
    img = Image.new("RGB", (w, h), bg)
    ic = icon.resize((icon_px, icon_px), Image.LANCZOS)
    img.paste(ic, ((w - icon_px) // 2, (h - icon_px) // 2), ic)
    img.save(os.path.join(OUT, name), "BMP")


os.makedirs(OUT, exist_ok=True)
for s, suffix in ((1, ""), (2, "200")):
    make(f"wizard{suffix}.bmp", 164 * s, 314 * s, 96 * s, (19, 19, 22))   # 앱 배경색 위에 아이콘
    make(f"small{suffix}.bmp", 55 * s, 55 * s, 48 * s, (255, 255, 255))
