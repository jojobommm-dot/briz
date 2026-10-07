"""Сборка фото для сайта: кадрирование и сжатие в WebP.

Исходники (как прислало кафе или как скачаны из их группы ВК) лежат в
data/photos_src — в git они не попадают, слишком тяжёлые. Готовые файлы
пишутся в static/img/briz и коммитятся.

Запуск:  venv\\Scripts\\python tools/photos.py
Нужен Pillow:  venv\\Scripts\\pip install pillow
"""

from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "data" / "photos_src"
OUT = BASE / "static" / "img" / "briz"

# имя → (исходник, (ширина, высота), (x, y) — куда сдвигать кадр, 0..1[, размытие])
# Почти все фото кафе вертикальные: для широких слайдов кадр выбираем руками
PHOTOS = {
    # слайды и шапки страниц, 16:9
    "hero-banket": ("briz_54.jpg", (1600, 900), (0.5, 0.62)),
    "hero-shashlik": ("briz_65.jpg", (1600, 900), (0.5, 0.55)),
    "hero-obed": ("briz_12.jpg", (1600, 900), (0.5, 0.5)),
    "hero-zal": ("briz_17.jpg", (1600, 900), (0.5, 0.45)),
    "hero-veranda": ("briz_59.jpg", (1600, 900), (0.5, 0.5)),
    # блюда для карусели, квадрат
    "dish-bolognese": ("briz_70.jpg", (600, 600), (0.5, 0.5)),
    "dish-carbonara": ("briz_80.jpg", (600, 600), (0.5, 0.45)),
    "dish-rostbif": ("briz_77.jpg", (600, 600), (0.5, 0.5)),
    "dish-sup-tykva": ("briz_85.jpg", (600, 600), (0.5, 0.45)),
    "dish-salat-kurica": ("briz_22.jpg", (600, 600), (0.5, 0.45)),
    "dish-shashlyk": ("briz_67.jpg", (600, 600), (0.5, 0.5)),
    "dish-caprese": ("briz_18.jpg", (600, 600), (0.5, 0.55)),
    # круглые фото (круг рисует CSS, файл квадратный)
    "round-obed": ("briz_64.jpg", (700, 700), (0.5, 0.5)),
    "round-shashlyk": ("briz_67.jpg", (900, 900), (0.5, 0.5)),
    # слайдер «меню недели»: по фото на день
    "week-1": ("briz_85.jpg", (900, 760), (0.5, 0.45)),
    "week-2": ("briz_70.jpg", (900, 760), (0.5, 0.5)),
    "week-3": ("briz_64.jpg", (900, 760), (0.5, 0.5)),
    "week-4": ("briz_22.jpg", (900, 760), (0.5, 0.45)),
    "week-5": ("briz_86.jpg", (900, 760), (0.5, 0.5)),
    # мозаика галереи
    "gal-wide": ("briz_55.jpg", (1600, 560), (0.5, 0.5)),
    "gal-hall": ("briz_54.jpg", (800, 760), (0.5, 0.55)),
    "gal-teal": ("briz_17.jpg", (800, 760), (0.5, 0.5)),
    "gal-veranda": ("briz_59.jpg", (420, 440), (0.5, 0.5)),
    "gal-mangal": ("briz_47.jpg", (420, 440), (0.5, 0.45)),
    "gal-table": ("briz_62.jpg", (420, 440), (0.5, 0.5)),
    "gal-pasta": ("briz_80.jpg", (420, 440), (0.5, 0.45)),
    # центр тарелки в «О Бризе»: блинные рулетики с лососем (фото прислал пользователь)
    "dish-blini": ("blini-losos.jpg", (700, 700), (0.53, 0.42)),
    # выездной кейтеринг: подносы с закусками, мангал, накрытый стол
    "kt-banner": ("briz_05.jpg", (1600, 900), (0.5, 0.55)),
    "kt-furshet": ("briz_04.jpg", (700, 700), (0.5, 0.5)),
    "kt-banket": ("briz_73.jpg", (700, 700), (0.5, 0.5)),
    "kt-shashlyk": ("briz_50.jpg", (700, 700), (0.5, 0.45)),
    "kt-obedy": ("briz_83.jpg", (700, 700), (0.5, 0.5)),
    "kt-trays": ("briz_05.jpg", (800, 800), (0.5, 0.6)),
    # фон блока «заявка на банкет»: размыт заранее, чтобы форма читалась
    "book-bg": ("briz_52.jpg", (1600, 800), (0.5, 0.5), 6),
}

QUALITY = 74


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, (src, size, centering, *blur) in PHOTOS.items():
        with Image.open(SRC / src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            fitted = ImageOps.fit(im, size, Image.Resampling.LANCZOS, centering=centering)
        if blur:
            fitted = fitted.filter(ImageFilter.GaussianBlur(blur[0]))
        dest = OUT / f"{name}.webp"
        fitted.save(dest, "WEBP", quality=QUALITY, method=6)
        kb = dest.stat().st_size // 1024
        total += kb
        print(f"{name:20} {size[0]}x{size[1]:<5} {kb:>4} КБ")
    print(f"Итого {len(PHOTOS)} файлов, {total} КБ")


if __name__ == "__main__":
    build()
