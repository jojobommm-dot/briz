"""Общий движок шаблонов и то, что видно во всех шаблонах."""

import re

from fastapi.templating import Jinja2Templates

from .config import settings
from .content import CAFE
from .security import CUSTOMER_COOKIE, CUSTOMER_DAYS, read_session

templates = Jinja2Templates(directory=settings.templates_root)


def _file_version(name: str) -> str:
    """Версия файла = время правки: меняется файл — меняется адрес."""
    try:
        return str(int((settings.static_root / name).stat().st_mtime))
    except OSError:
        return "0"


def asset(name: str) -> str:
    """Адрес файла из static с меткой правки, чтобы браузер не показывал
    вчерашний стиль из кеша. Имя относительно static/: asset("css/site.css")."""
    return f"/static/{name}?v={_file_version(name)}"


def _phone(v: str | None) -> str:
    """+73422837704 → +7 (342) 283-77-04. Остальное отдаём как есть."""
    digits = re.sub(r"\D", "", v or "")
    if len(digits) != 11:
        return v or ""
    return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:]}"


def _rub(v: int) -> str:
    """1500 → «1 500 ₽» с неразрывными пробелами."""
    return f"{v:,}".replace(",", " ") + " ₽"


def _customer_logged_in(request) -> bool:
    """Шапке: «Кабинет» или «Войти». Только подпись куки, без похода в базу."""
    return read_session(request.cookies.get(CUSTOMER_COOKIE), "c", CUSTOMER_DAYS) is not None


templates.env.globals["asset"] = asset
templates.env.globals["customer_logged_in"] = _customer_logged_in
templates.env.globals["cafe"] = CAFE
templates.env.globals["debug"] = settings.debug
templates.env.globals["base_url"] = settings.base_url
# Статичная копия для GitHub Pages (tools/freeze.py): без сервера — без кабинета,
# онлайн-заказа, отправки заявок и приложения; вместо них звонок и ВКонтакте
templates.env.globals["static_site"] = False
templates.env.filters["phone"] = _phone
templates.env.filters["rub"] = _rub
