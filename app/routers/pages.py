"""Публичные страницы сайта."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from .. import banquet
from ..config import settings
from ..content import (
    BANQUET_FACTS,
    BANQUET_PACKAGES,
    HERO_SLIDES,
    LUNCH,
    MENU,
    SERVICES,
    popular_dishes,
)
from ..templating import templates

router = APIRouter()
log = logging.getLogger("briz")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "slides": HERO_SLIDES,
            "services": SERVICES,
            "popular": popular_dishes(),
            "packages": BANQUET_PACKAGES,
            "facts": BANQUET_FACTS,
            "lunch": LUNCH,
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
async def banket(request: Request, paket: str = ""):
    # ?paket=svadba с главной — сразу отмечаем нужный пакет
    form = {"package": paket} if paket in banquet.PACKAGE_SLUGS else {}
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
    return templates.TemplateResponse(request, "banket_thanks.html", {"nav": "banket"})


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
