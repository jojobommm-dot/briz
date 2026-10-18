"""Статичная копия сайта для GitHub Pages — как сайт coffe: только страницы, без сервера.

    python tools/freeze.py _site --base-url https://jojobommm-dot.github.io/briz

Страницы рисуются тем же приложением в «статичном режиме» (templates: static_site):
без кабинета, онлайн-заказа, отправки заявок и установки приложения — вместо них
звонок и ВКонтакте. Сайт на Pages живёт в подпапке (/briz/), поэтому адреса вида
/menu и /static/… переписываются под неё. Ссылка на страницу, которой в копии нет, —
ошибка сборки, а не битая ссылка у гостя.

Собирает и выкладывает GitHub Actions (.github/workflows/pages.yml) после каждого push.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Страница → файл. Pages отдаёт /menu из menu.html сам
PAGES = {
    "/": "index.html",
    "/menu": "menu.html",
    "/obedy": "obedy.html",
    "/banket": "banket.html",
    "/keytering": "keytering.html",
    "/kontakty": "kontakty.html",
}

# href="/…", src="/…", url('/…') — но не //cdn… и не https://…
_ATTR = re.compile(r"""(\b(?:href|src|action)=["'])/(?!/)""")
_CSS_URL = re.compile(r"""(url\(["']?)/(?!/)""")


def rebase(text: str, prefix: str) -> str:
    """/menu → /briz/menu. prefix со слэшем на конце: "/briz/" или "/"."""
    if prefix == "/":
        return text
    text = _ATTR.sub(lambda m: m.group(1) + prefix, text)
    return _CSS_URL.sub(lambda m: m.group(1) + prefix, text)


def broken_links(out: Path, prefix: str) -> list[str]:
    """Внутренние ссылки страниц, для которых в копии нет файла."""
    missing = set()
    for html in out.glob("*.html"):
        for url in re.findall(r"""\b(?:href|src)=["']([^"']+)""", html.read_text(encoding="utf-8")):
            path = urlsplit(url).path
            if urlsplit(url).scheme or not path.startswith(prefix):
                continue
            rel = path[len(prefix) :]
            target = out / rel if rel else out / "index.html"
            if not target.is_file() and not (out / f"{rel}.html").is_file():
                missing.add(f"{html.name}: {url}")
    return sorted(missing)


def build(out: Path, base_url: str) -> None:
    """Собирает копию в out. Настройки приложения возвращает как были — для тестов."""
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app
    from app.templating import templates

    base_url = base_url.rstrip("/")
    prefix = (urlsplit(base_url).path.rstrip("/") or "") + "/"
    saved = settings.base_url, dict(templates.env.globals)
    settings.base_url = base_url
    templates.env.globals.update(static_site=True, debug=False, base_url=base_url)
    try:
        # Без lifespan: базе в статичной копии делать нечего
        client = TestClient(app)
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(settings.static_root, out / "static")
        for css in (out / "static" / "css").glob("*.css"):
            css.write_text(rebase(css.read_text(encoding="utf-8"), prefix), encoding="utf-8")

        for url, name in PAGES.items():
            r = client.get(url)
            r.raise_for_status()
            (out / name).write_text(rebase(r.text, prefix), encoding="utf-8")
        r = client.get("/net-takoy-stranicy")
        assert r.status_code == 404
        (out / "404.html").write_text(rebase(r.text, prefix), encoding="utf-8")
    finally:
        settings.base_url = saved[0]
        templates.env.globals.clear()
        templates.env.globals.update(saved[1])

    (out / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")  # Pages не трогает файлы

    missing = broken_links(out, prefix)
    if missing:
        raise SystemExit(
            "Ссылки на страницы, которых нет в статичной копии:\n  " + "\n  ".join(missing)
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out", type=Path, help="куда собрать, например _site")
    ap.add_argument("--base-url", required=True, help="адрес сайта без слэша на конце")
    args = ap.parse_args()
    build(args.out, args.base_url)
    print(f"Собрано в {args.out}: {len(PAGES)} страниц + 404, адрес {args.base_url.rstrip('/')}/")


if __name__ == "__main__":
    main()
