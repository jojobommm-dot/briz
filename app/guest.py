"""Гость без кабинета: метка браузера в долгой куке и перенос его заказов в кабинет.

Кто заказал без регистрации, получает подписанную куку briz_guest со случайной
меткой; ею же помечаются его заказы обедов и брони столов. Так при повторном
заходе — сегодня или через месяц, к брони на далёкую дату — он видит свои
заказы и может их изменить, а не оформить второй раз.

Когда гость регистрируется или входит, его заказы переезжают в кабинет, если
совпадает телефон и одно из двух: заказ сделан из этого же браузера (метка)
или гость знает ссылку на заказ (токен). Одного телефона мало: номер при
регистрации пока не подтверждается, и по чужому номеру нельзя увидеть чужие
адреса и заказы. С подтверждением по СМС условие можно ослабить до телефона.
"""

import secrets
from collections.abc import Iterable

from fastapi import Request, Response
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import Booking, Customer, Order

GUEST_COOKIE = "briz_guest"
GUEST_DAYS = 400  # дольше браузеры куку не хранят; продлевается с каждым заказом


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.secret_key, salt="briz-guest")


def guest_key(request: Request) -> str:
    """Метка гостя из куки; нет куки или подпись не сошлась — пустая строка."""
    value = request.cookies.get(GUEST_COOKIE)
    if not value:
        return ""
    try:
        key = _serializer().loads(value)
    except BadSignature:
        return ""
    return key if isinstance(key, str) and len(key) == 32 else ""


def ensure_guest(request: Request, response: Response) -> str:
    """Метка гостя: прежняя или новая. Кука продлевается на GUEST_DAYS."""
    key = guest_key(request) or secrets.token_hex(16)
    response.set_cookie(
        GUEST_COOKIE,
        _serializer().dumps(key),
        max_age=GUEST_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.base_url.startswith("https"),
    )
    return key


async def claim(
    session: AsyncSession, customer: Customer, key: str, tokens: Iterable[str] = ()
) -> int:
    """Перенести в кабинет заказы и брони гостя: тот же телефон и (та же метка или
    известна ссылка). Возвращает, сколько перенесли; commit — за вызывающим."""
    tokens = [t for t in tokens if isinstance(t, str)][:50]
    moved = 0
    for model in (Order, Booking):
        proof = []
        if key:
            proof.append(model.guest_key == key)
        if tokens:
            proof.append(model.token.in_(tokens))
        if not proof:
            continue
        rows = (
            await session.scalars(
                select(model).where(
                    model.customer_id.is_(None), model.phone == customer.phone, or_(*proof)
                )
            )
        ).all()
        for row in rows:
            row.customer_id = customer.id
        moved += len(rows)
    return moved
