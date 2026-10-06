"""Иконки PWA из фирменного знака (круг с двумя волнами).

SVG-знак рисуем заново через Pillow: конвертеров SVG в проекте нет, а
знак простой. Рисуем в 4 раза крупнее и уменьшаем — так края гладкие.

Запуск:  venv\\Scripts\\python tools/icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "static" / "icons"

# Фон — тёмный, как шапка сайта; волны — золотом (стиль по эталону Restora)
GREEN = (12, 15, 20)
WHITE = (167, 137, 99)
# Вторая волна приглушённая: золото на 55% поверх фона
PALE = tuple(round(b + (g - b) * 0.55) for b, g in zip(GREEN, WHITE, strict=True))

# Волна из sprite.svg в координатах 40×40: три кубические кривые Безье
WAVE = [
    ((7, 19), (10.2, 16), (13.4, 16), (16.6, 19)),
    ((16.6, 19), (19.8, 22), (23, 22), (26.2, 19)),
    ((26.2, 19), (29.4, 16), (30.8, 16.8), (33, 18)),
]


def _bezier(p0, p1, p2, p3, steps=24):
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        yield (
            mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0],
            mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1],
        )


def _draw_mark(draw: ImageDraw.ImageDraw, ox: float, oy: float, scale: float) -> None:
    """Две волны знака; (ox, oy) — где окажется точка (0, 0) знака."""
    width = 2.6 * scale
    for dy, color in ((0, WHITE), (7, PALE)):
        pts = []
        for seg in WAVE:
            pts.extend((ox + x * scale, oy + (y + dy) * scale) for x, y in _bezier(*seg))
        draw.line(pts, fill=color, width=round(width), joint="curve")
        for x, y in (pts[0], pts[-1]):  # скруглённые концы, как stroke-linecap="round"
            r = width / 2
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


def icon(size: int, maskable: bool = False) -> Image.Image:
    big = size * 4
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if maskable:
        # Система сама обрежет иконку кругом или «каплей»: фон до краёв,
        # знак в безопасной зоне (центральные 80%)
        # Волны занимают по ширине 26 единиц из 40 (x от 7 до 33), по высоте
        # центр на y=22.5 — растягиваем их на 62% иконки и ставим по центру
        d.rectangle((0, 0, big, big), fill=GREEN)
        scale = big * 0.62 / 26
        _draw_mark(d, big / 2 - 20 * scale, big / 2 - 22.5 * scale, scale)
    else:
        d.ellipse((0, 0, big - 1, big - 1), fill=GREEN)
        _draw_mark(d, 0, 0, big / 40)
    return im.resize((size, size), Image.Resampling.LANCZOS)


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    icon(192).save(OUT / "icon-192.png")
    icon(512).save(OUT / "icon-512.png")
    icon(512, maskable=True).save(OUT / "icon-maskable-512.png")
    # iOS берёт apple-touch-icon и сам скругляет углы — прозрачность ему не нужна
    icon(180, maskable=True).convert("RGB").save(OUT / "apple-touch-icon.png")
    icon(32).save(OUT / "favicon-32.png")
    # Ярлыки для долгого нажатия на иконку (shortcuts в манифесте)
    for name in ("banket", "obedy", "menu"):
        icon(96, maskable=True).save(OUT / f"shortcut-{name}.png")
    print("Иконки готовы:", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    build()
