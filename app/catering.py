"""Заявка на выездной кейтеринг: проверка полей и сохранение.

Как и банкетные, до базы (шаг 2) заявки пишутся построчно в
data/catering_requests.jsonl — потом переедут в таблицу заявок и в ленту
менеджера.
"""

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime

from .banquet import normalize_phone, parse_date
from .config import settings
from .content import CATERING_FORMATS

FORMAT_SLUGS = {f.slug for f in CATERING_FORMATS}
GUESTS_MIN, GUESTS_MAX = 5, 500


@dataclass
class CateringRequest:
    name: str
    phone: str
    event_date: str
    guests: int
    format: str
    place: str
    comment: str


def validate(
    form: dict[str, str], today: date | None = None
) -> tuple[CateringRequest | None, dict]:
    today = today or date.today()
    errors: dict[str, str] = {}

    name = form.get("name", "").strip()
    if not 2 <= len(name) <= 80:
        errors["name"] = "Как к вам обращаться?"

    phone = normalize_phone(form.get("phone", ""))
    if phone is None:
        errors["phone"] = "Нужен номер из 10–11 цифр, например 8 912 345-67-89"

    event_date = parse_date(form.get("event_date", ""))
    if event_date is None:
        errors["event_date"] = "Выберите дату мероприятия"
    elif event_date < today:
        errors["event_date"] = "Эта дата уже прошла"

    try:
        guests = int(form.get("guests", ""))
    except ValueError:
        guests = 0
    if not GUESTS_MIN <= guests <= GUESTS_MAX:
        errors["guests"] = f"Принимаем заказы от {GUESTS_MIN} до {GUESTS_MAX} гостей"

    fmt = form.get("format", "")
    if fmt not in FORMAT_SLUGS:
        errors["format"] = "Выберите формат"

    place = form.get("place", "").strip()
    if not 3 <= len(place) <= 200:
        errors["place"] = "Куда привезти: адрес или название места"

    comment = form.get("comment", "").strip()[:1000]

    if errors:
        return None, errors
    return CateringRequest(name, phone, event_date.isoformat(), guests, fmt, place, comment), {}


def save(req: CateringRequest) -> None:
    settings.data_root.mkdir(parents=True, exist_ok=True)
    line = {"created_at": datetime.now().isoformat(timespec="seconds"), **asdict(req)}
    with (settings.data_root / "catering_requests.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
