"""Иконки PWA из логотипа.

- Иконки приложения (180–512 px) — настоящий знак static/img/logo/briz-mark.svg.
  Pillow не умеет SVG, поэтому знак отрисовывает установленный Chrome
  (headless, прозрачный фон), а Pillow уменьшает и кладёт на фон.
- Мелкие (вкладка браузера, 32 px) — упрощённый знак static/icons/icon.svg:
  в листе бренда прямо сказано, что на 32 px сцена логотипа сливается в пятно.

Запуск:  venv\\Scripts\\python tools/icons.py
"""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "static" / "icons"
MARK = BASE / "static" / "img" / "logo" / "briz-mark.svg"
SIMPLE = OUT / "icon.svg"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

NIGHT = (8, 47, 64, 255)  # --dark сайта: фон под знаком, где нужен сплошной


def render_svg(svg: Path, size: int = 1024) -> Image.Image:
    """SVG → PNG нужного размера через headless Chrome.

    Окно меньше ~500 px Chrome не делает, поэтому рисуем крупно и уменьшаем."""
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(
            f'<html><body style="margin:0;background:transparent">'
            f'<img src="{svg.as_uri()}" style="width:{size}px;height:{size}px;display:block">'
            f"</body></html>",
            encoding="utf-8",
        )
        shot = Path(tmp) / "shot.png"
        subprocess.run(
            [
                str(CHROME),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--user-data-dir={Path(tmp) / 'profile'}",
                "--default-background-color=00000000",
                f"--window-size={size},{size}",
                f"--screenshot={shot}",
                page.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return Image.open(shot).convert("RGBA").crop((0, 0, size, size))


def on_background(mark: Image.Image, size: int, scale: float) -> Image.Image:
    """Знак на сплошном ночном фоне: для maskable и iPhone (они не любят прозрачность)."""
    bg = Image.new("RGBA", (size, size), NIGHT)
    inner = round(size * scale)
    m = mark.resize((inner, inner), Image.Resampling.LANCZOS)
    bg.alpha_composite(m, ((size - inner) // 2, (size - inner) // 2))
    return bg


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mark = render_svg(MARK)
    simple = render_svg(SIMPLE)

    mark.resize((512, 512), Image.Resampling.LANCZOS).save(OUT / "icon-512.png")
    mark.resize((192, 192), Image.Resampling.LANCZOS).save(OUT / "icon-192.png")
    # Android сам обрежет кругом или «каплей»: знак в безопасной зоне 80%
    on_background(mark, 512, 0.86).save(OUT / "icon-maskable-512.png")
    # iOS сам скругляет углы, прозрачность заливает чёрным — даём свой фон
    on_background(mark, 180, 0.92).convert("RGB").save(OUT / "apple-touch-icon.png")
    simple.resize((32, 32), Image.Resampling.LANCZOS).save(OUT / "favicon-32.png")
    for name in ("banket", "obedy", "menu"):
        on_background(simple, 96, 0.86).save(OUT / f"shortcut-{name}.png")
    print("Иконки готовы:", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    build()
