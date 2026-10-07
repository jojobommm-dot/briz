"""Публичные страницы сайта."""

import hashlib
import logging

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse

from .. import banquet, catering
from ..config import settings
from ..content import (
    BANQUET_FACTS,
    BANQUET_PACKAGES,
    CAFE,
    CATERING_FORMATS,
    CATERING_STEPS,
    GALLERY,
    HERO_SLIDES,
    LUNCH,
    MENU,
    WEEK_IMAGES,
    popular_dishes,
)
from ..templating import asset, templates

router = APIRouter()
log = logging.getLogger("briz")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "slides": HERO_SLIDES,
            "popular": popular_dishes(),
            "packages": BANQUET_PACKAGES,
            "facts": BANQUET_FACTS,
            "lunch": LUNCH,
            "week": list(zip(LUNCH["week"], WEEK_IMAGES, strict=True)),
            "menu": MENU,
            "gallery": GALLERY,
            "catering": CATERING_FORMATS,
            "nav": "home",
        },
    )


@router.get("/menu", response_class=HTMLResponse)
async def menu(request: Request):
    return templates.TemplateResponse(request, "menu.html", {"menu": MENU, "nav": "menu"})


def _banket_page(request: Request, form: dict | None = None, errors: dict | None = None):
    return templates.TemplateResponse(
        request,
        "banket.html",
        {
            "packages": BANQUET_PACKAGES,
            "facts": BANQUET_FACTS,
            "form": form or {},
            "errors": errors or {},
            "nav": "banket",
        },
        status_code=422 if errors else 200,
    )


@router.get("/banket", response_class=HTMLResponse)
async def banket(request: Request, paket: str = "", date: str = "", guests: str = ""):
    # С главной приходят ?paket=svadba&date=2026-11-14&guests=25 — подставляем в форму,
    # но только то, что похоже на правду: остальное гость введёт сам
    form = {}
    if paket in banquet.PACKAGE_SLUGS:
        form["package"] = paket
    if banquet.parse_date(date):
        form["event_date"] = date
    if guests.isdigit() and 1 <= int(guests) <= CAFE["capacity"]:
        form["guests"] = guests
    return _banket_page(request, form)


@router.post("/banket/zayavka")
async def banket_request(request: Request):
    form = {k: str(v) for k, v in (await request.form()).items()}
    req, errors = banquet.validate(form)
    if req is None:
        return _banket_page(request, form, errors)
    banquet.save(req)
    log.info("Заявка на банкет: %s, %s гостей, %s", req.event_date, req.guests, req.package)
    # PRG: обновление страницы «спасибо» не отправит заявку второй раз
    return RedirectResponse("/banket/spasibo", status_code=303)


@router.get("/banket/spasibo", response_class=HTMLResponse)
async def banket_thanks(request: Request):
    return templates.TemplateResponse(
        request,
        "thanks.html",
        {
            "nav": "banket",
            "lead": "Перезвоним в течение часа в рабочее время, подтвердим дату и обсудим меню.",
        },
    )


def _keytering_page(request: Request, form: dict | None = None, errors: dict | None = None):
    return templates.TemplateResponse(
        request,
        "keytering.html",
        {
            "formats": CATERING_FORMATS,
            "steps": CATERING_STEPS,
            "form": form or {},
            "errors": errors or {},
            "guests_min": catering.GUESTS_MIN,
            "guests_max": catering.GUESTS_MAX,
            "nav": "keytering",
        },
        status_code=422 if errors else 200,
    )


@router.get("/keytering", response_class=HTMLResponse)
async def keytering(request: Request, format: str = ""):
    # ?format=shashlyk с карточки формата — сразу отмечаем его в заявке
    return _keytering_page(request, {"format": format} if format in catering.FORMAT_SLUGS else {})


@router.post("/keytering/zayavka")
async def keytering_request(request: Request):
    form = {k: str(v) for k, v in (await request.form()).items()}
    req, errors = catering.validate(form)
    if req is None:
        return _keytering_page(request, form, errors)
    catering.save(req)
    log.info("Заявка на кейтеринг: %s, %s гостей, %s", req.event_date, req.guests, req.format)
    return RedirectResponse("/keytering/spasibo", status_code=303)


@router.get("/keytering/spasibo", response_class=HTMLResponse)
async def keytering_thanks(request: Request):
    return templates.TemplateResponse(
        request,
        "thanks.html",
        {
            "nav": "keytering",
            "lead": "Перезвоним в рабочее время, уточним формат и место и посчитаем стоимость.",
        },
    )


@router.get("/obedy", response_class=HTMLResponse)
async def lunch(request: Request):
    return templates.TemplateResponse(request, "lunch.html", {"lunch": LUNCH, "nav": "obedy"})


@router.get("/kontakty", response_class=HTMLResponse)
async def contacts(request: Request):
    return templates.TemplateResponse(request, "contacts.html", {"nav": "kontakty"})


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    # Пока сайт на тестовом поддомене, поисковикам в него рано
    if settings.debug:
        return "User-agent: *\nDisallow: /\n"
    return f"User-agent: *\nAllow: /\nSitemap: {settings.base_url}/sitemap.xml\n"


# --- PWA ---

# Файлы оболочки: без них установленное приложение не откроется без сети
_SHELL_ASSETS = [
    "css/site.css",
    "js/site.js",
    "icons/sprite.svg",
    "icons/icon-192.png",
    "img/logo/briz-mark.svg",
]
_SHELL_PAGES = ["/", "/zakaz", "/menu", "/obedy", "/kontakty", "/offline"]


def _sw_version() -> str:
    """Версия кеша = отпечаток времени правки оболочки и самого воркера."""
    files = [settings.static_root / a for a in _SHELL_ASSETS]
    files += [settings.static_root / "manifest.webmanifest", settings.templates_root / "sw.js"]
    stamp = "|".join(str(f.stat().st_mtime_ns) for f in files if f.exists())
    return hashlib.sha1(stamp.encode()).hexdigest()[:10]


@router.get("/sw.js")
async def service_worker(request: Request):
    # С корня, а не из /static: воркер управляет только адресами ниже своего
    return templates.TemplateResponse(
        request,
        "sw.js",
        {"version": _sw_version(), "precache": _SHELL_PAGES + [asset(a) for a in _SHELL_ASSETS]},
        media_type="application/javascript",
        # Браузер должен всегда спрашивать свежий воркер, иначе обновления застрянут
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(
        settings.static_root / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/offline", response_class=HTMLResponse)
async def offline(request: Request):
    return templates.TemplateResponse(request, "offline.html", {"nav": ""})
