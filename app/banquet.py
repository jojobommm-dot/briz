"""Заявка на банкет: проверка полей. Сохраняет в базу app/leads.py."""

import re
from dataclasses import dataclass
from datetime import date

from .content import BANQUET_PACKAGES, CAFE

PACKAGE_SLUGS = {p.slug for p in BANQUET_PACKAGES}


@dataclass
class BanquetRequest:
    name: str
    phone: str  # +7XXXXXXXXXX
    event_date: str  # YYYY-MM-DD
    guests: int
    package: str
    comment: str


def normalize_phone(raw: str) -> str | None:
    """8 912 345-67-89, +7(912)3456789, 9123456789 → +79123456789."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    return None


def parse_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def validate(form: dict[str, str], today: date | None = None) -> tuple[BanquetRequest | None, dict]:
    """Возвращает заявку или словарь «поле → что не так» для формы."""
    today = today or date.today()
    errors: dict[str, str] = {}

    name = form.get("name", "").strip()
    if not 2 <= len(name) <= 80:
        errors["name"] = "Как к вам обращаться?"

    phone = normalize_phone(form.get("phone", ""))
    if phone is None:
        errors["phone"] = "Нужен номер из 10–11 цифр, например 8 912 345-67-89"

    event_date = None
    try:
        event_date = date.fromisoformat(form.get("event_date", ""))
    except ValueError:
        errors["event_date"] = "Выберите дату праздника"
    else:
        if event_date < today:
            errors["event_date"] = "Эта дата уже прошла"
        elif (event_date - today).days > 730:
            errors["event_date"] = "Принимаем заявки не дальше чем на два года вперёд"

    try:
        guests = int(form.get("guests", ""))
    except ValueError:
        guests = 0
    if not 1 <= guests <= CAFE["capacity"]:
        errors["guests"] = f"В зале от 1 до {CAFE['capacity']} гостей"

    package = form.get("package", "")
    if package not in PACKAGE_SLUGS:
        errors["package"] = "Выберите пакет"

    comment = form.get("comment", "").strip()[:1000]

    if errors:
        return None, errors
    return BanquetRequest(name, phone, event_date.isoformat(), guests, package, comment), {}
