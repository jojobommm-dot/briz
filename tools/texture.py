"""Бумажное зерно для всего сайта — «печатный» вид, как у винилового яблока.

Плитка 256×256: редкие чёрные и белые крапинки с малой прозрачностью.
Белые видны на тёмных блоках, чёрные — на светлых; плитка бесшовная,
потому что каждый пиксель случаен и не зависит от соседей.

Запуск:  venv\\Scripts\\python tools/texture.py
"""

import random
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "static" / "img" / "grain.png"
SIZE = 256


def build(seed: int = 7) -> None:
    rnd = random.Random(seed)  # одно и то же зерно при каждой сборке — без лишних правок в git
    im = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    px = im.load()
    for y in range(SIZE):
        for x in range(SIZE):
            r = rnd.random()
            if r < 0.20:
                px[x, y] = (0, 0, 0, rnd.randint(10, 34))
            elif r < 0.32:
                px[x, y] = (255, 255, 255, rnd.randint(8, 26))
    im.save(OUT, optimize=True)
    print(f"{OUT.name}: {OUT.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    build()
