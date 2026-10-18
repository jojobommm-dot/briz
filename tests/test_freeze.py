"""Статичная копия для GitHub Pages: собирается, ссылки под /briz/, без серверных частей."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "freeze", Path(__file__).resolve().parent.parent / "tools" / "freeze.py"
)
freeze = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(freeze)


def test_static_copy(tmp_path, client):
    out = tmp_path / "site"
    freeze.build(out, "https://jojobommm-dot.github.io/briz")

    for name in [*freeze.PAGES.values(), "404.html", ".nojekyll", "static/css/site.css"]:
        assert (out / name).is_file(), name
    home = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="/briz/menu"' in home and 'href="/menu"' not in home
    assert "/zakaz" not in home and "/kabinet" not in home and "manifest" not in home
    assert "data-static" in home
    banket = (out / "banket.html").read_text(encoding="utf-8")
    assert "/banket/zayavka" not in banket and 'href="tel:+73422837704"' in banket
    assert 'url("/briz/static/' in (out / "static/css/site.css").read_text(encoding="utf-8")

    # После сборки обычный сайт — снова с онлайн-заказом и кабинетом
    page = client.get("/").text
    assert 'href="/zakaz"' in page and "data-static" not in page


def test_rebase_leaves_external_links():
    html = '<a href="/menu"><img src="//cdn.x/a.png"><a href="https://vk.com/x"> url(\'/static/a.webp\')'
    assert freeze.rebase(html, "/briz/") == (
        '<a href="/briz/menu"><img src="//cdn.x/a.png"><a href="https://vk.com/x"> url(\'/briz/static/a.webp\')'
    )
