"""Сборка фото для сайта: кадрирование и сжатие в WebP.

Исходники (как прислало кафе или как скачаны из их группы ВК) лежат в
data/photos_src — в git они не попадают, слишком тяжёлые. Готовые файлы
пишутся в static/img/briz и коммитятся.

Запуск:  venv\\Scripts\\python tools/photos.py
Нужен Pillow:  venv\\Scripts\\pip install pillow
"""

from pathlib import Path

from PIL import Image, ImageOps

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "data" / "photos_src"
OUT = BASE / "static" / "img" / "briz"

# имя → (исходник, (ширина, высота), (x, y) — куда сдвигать кадр, 0..1)
# Почти все фото кафе вертикальные: для широких слайдов кадр выбираем руками
PHOTOS = {
    # слайды и шапки страниц, 16:9
    "hero-banket": ("briz_54.jpg", (1600, 900), (0.5, 0.62)),
    "hero-shashlik": ("briz_65.jpg", (1600, 900), (0.5, 0.55)),
    "hero-obed": ("briz_12.jpg", (1600, 900), (0.5, 0.5)),
    "hero-zal": ("briz_17.jpg", (1600, 900), (0.5, 0.45)),
    "hero-veranda": ("briz_59.jpg", (1600, 900), (0.5, 0.5)),
    # миниатюры нумерованного списка
    "thumb-banket": ("briz_52.jpg", (240, 240), (0.5, 0.55)),
    "thumb-obed": ("briz_23.jpg", (240, 240), (0.5, 0.5)),
    "thumb-dostavka": ("briz_83.jpg", (240, 240), (0.5, 0.5)),
    "thumb-mangal": ("briz_47.jpg", (240, 240), (0.5, 0.4)),
    "thumb-svadba": ("briz_56.jpg", (240, 240), (0.5, 0.6)),
    "thumb-furshet": ("briz_04.jpg", (240, 240), (0.5, 0.5)),
    # блюда для карусели, квадрат
    "dish-bolognese": ("briz_70.jpg", (600, 600), (0.5, 0.5)),
    "dish-carbonara": ("briz_80.jpg", (600, 600), (0.5, 0.45)),
    "dish-rostbif": ("briz_77.jpg", (600, 600), (0.5, 0.5)),
    "dish-sup-tykva": ("briz_85.jpg", (600, 600), (0.5, 0.45)),
    "dish-salat-kurica": ("briz_22.jpg", (600, 600), (0.5, 0.45)),
    "dish-shashlyk": ("briz_67.jpg", (600, 600), (0.5, 0.5)),
    "dish-caprese": ("briz_18.jpg", (600, 600), (0.5, 0.55)),
    # крупные блоки главной
    "about-zal": ("briz_53.jpg", (800, 800), (0.5, 0.55)),
    "promo-banket": ("briz_62.jpg", (900, 1100), (0.5, 0.5)),
    "story-obed": ("briz_23.jpg", (900, 900), (0.5, 0.5)),
    "story-dostavka": ("briz_11.jpg", (900, 900), (0.5, 0.5)),
}

QUALITY = 74


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, (src, size, centering) in PHOTOS.items():
        with Image.open(SRC / src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            fitted = ImageOps.fit(im, size, Image.Resampling.LANCZOS, centering=centering)
        dest = OUT / f"{name}.webp"
        fitted.save(dest, "WEBP", quality=QUALITY, method=6)
        kb = dest.stat().st_size // 1024
        total += kb
        print(f"{name:20} {size[0]}x{size[1]:<5} {kb:>4} КБ")
    print(f"Итого {len(PHOTOS)} файлов, {total} КБ")


if __name__ == "__main__":
    build()
