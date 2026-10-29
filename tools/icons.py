"""Логотип «Бриза» во всех видах — из одного исходника art/briz-logo.png.

Исходник — круглый знак 1000×1000 с прозрачными углами и свечением по краю
(октябрь 2026: девушка в белом платье и на белых каблуках у столика на берегу
Камы, луна, свеча). Из него собираются:
- static/img/logo/briz-mark.webp — знак для страниц: шапка, пластинка, входы;
- static/img/logo/*.svg — фирменные файлы: знак и надпись «БРИЗ / кафе на берегу
  Камы», вертикально и горизонтально, для тёмного и светлого фона. Надпись —
  прежние кривые Cormorant Garamond, знак вложен картинкой в base64: SVG через
  <img> внешние файлы не подгружает;
- static/icons/*.png — иконки PWA, iPhone, вкладки браузера и ярлыков.

Новый логотип — заменить art/briz-logo.png и запустить:
    venv\\Scripts\\python tools/icons.py
"""

import base64
import io
import re
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "art" / "briz-logo.png"
LOGO = BASE / "static" / "img" / "logo"
ICONS = BASE / "static" / "icons"

NIGHT = (8, 47, 64, 255)  # --dark сайта: фон под знаком, где нужен сплошной

# В фирменных SVG знак занимает квадрат 400×400 в начале координат, а надпись —
# кривые со сдвигом (transform); их и корневой тег с viewBox сохраняем как были
WORDMARK = re.compile(r'<path transform="translate\([^"]+\)"[^>]*/>')
SVG_TAG = re.compile(r"<svg\b[^>]*>")


def scaled(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.Resampling.LANCZOS)


def on_background(mark: Image.Image, size: int, scale: float) -> Image.Image:
    """Знак на сплошном ночном фоне: для maskable и iPhone (они не любят прозрачность)."""
    bg = Image.new("RGBA", (size, size), NIGHT)
    inner = round(size * scale)
    bg.alpha_composite(scaled(mark, inner), ((size - inner) // 2,) * 2)
    return bg


def webp(mark: Image.Image, size: int, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    scaled(mark, size).save(buf, "WEBP", quality=quality, method=6)
    return buf.getvalue()


def brand_svgs(mark: Image.Image) -> None:
    data = base64.b64encode(webp(mark, 480, 88)).decode()
    image = (
        f'  <image href="data:image/webp;base64,{data}" x="0" y="0" width="400" height="400"/>\n'
    )
    for f in sorted(LOGO.glob("*.svg")):
        s = f.read_text(encoding="utf-8")
        words = "".join(f"  {w}\n" for w in WORDMARK.findall(s))
        f.write_text(
            f"{SVG_TAG.search(s).group(0)}\n{image}{words}</svg>\n", encoding="utf-8", newline="\n"
        )


def build() -> None:
    mark = Image.open(SRC).convert("RGBA")
    (LOGO / "briz-mark.webp").write_bytes(webp(mark, 640))
    brand_svgs(mark)

    ICONS.mkdir(parents=True, exist_ok=True)
    scaled(mark, 512).save(ICONS / "icon-512.png")
    scaled(mark, 192).save(ICONS / "icon-192.png")
    # Android сам обрежет кругом или «каплей»: знак в безопасной зоне 80%
    on_background(mark, 512, 0.86).save(ICONS / "icon-maskable-512.png")
    # iOS сам скругляет углы, прозрачность заливает чёрным — даём свой фон
    on_background(mark, 180, 0.92).convert("RGB").save(ICONS / "apple-touch-icon.png")
    scaled(mark, 32).save(ICONS / "favicon-32.png")
    for name in ("banket", "obedy", "menu"):
        on_background(mark, 96, 0.86).save(ICONS / f"shortcut-{name}.png")
    files = [*LOGO.iterdir(), *ICONS.glob("*.png")]
    print("Логотип и иконки готовы:", ", ".join(sorted(p.name for p in files)))


if __name__ == "__main__":
    build()
