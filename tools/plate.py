"""Тарелка для блока «О Бризе»: вырезаем круг тарелки из белого фона фото.

Исходник — фото сверху на белом фоне (data/photos_src/plate-mix-blue.png,
тарелка обеденная 26,5 см Mix, глазурованная керамика, каталог posudacenter.ru).
Края тарелки ищем по пикселям, заметно темнее фона; вокруг — прозрачность
с мягким краем, чтобы тарелка легла на тёмный фон сайта без ореола.

Запуск:  venv\\Scripts\\python tools/plate.py
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "data" / "photos_src" / "plate-mix-blue.png"
OUT = BASE / "static" / "img" / "briz" / "plate-blue.webp"
SIZE = 900


def build() -> None:
    im = Image.open(SRC).convert("RGB")
    # Что заметно отличается от белого — тарелка (тень у неё мягкая и светлая)
    diff = ImageChops.difference(im, Image.new("RGB", im.size, "white")).convert("L")
    left, top, right, bottom = diff.point(lambda v: 255 if v > 40 else 0).getbbox()
    d = max(right - left, bottom - top)
    cx, cy = (left + right) / 2, (top + bottom) / 2
    box = (round(cx - d / 2), round(cy - d / 2), round(cx + d / 2), round(cy + d / 2))
    plate = im.crop(box).resize((SIZE, SIZE), Image.Resampling.LANCZOS).convert("RGBA")

    # Круглая маска чуть меньше края: убираем белую кайму фона
    mask = Image.new("L", (SIZE * 4, SIZE * 4), 0)
    ImageDraw.Draw(mask).ellipse((10, 10, SIZE * 4 - 10, SIZE * 4 - 10), fill=255)
    mask = mask.resize((SIZE, SIZE), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(0.6))
    plate.putalpha(mask)
    plate.save(OUT, "WEBP", quality=82, method=6)
    print(f"{OUT.name}: {SIZE}x{SIZE}, {OUT.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    build()
