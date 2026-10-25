"""Личный кабинет гостя: вход, регистрация, заказы, адреса, профиль.

Вход по телефону и паролю — работает без внешних сервисов. Подтверждение
телефона по СМС или вход через VK ID — следующим шагом (кабинет к этому готов:
меняется только способ входа).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import lunch_order as lo
from ..auth import current_customer, login_customer, logout, require_customer
from ..banquet import PHONE_ERROR, normalize_phone
from ..database import get_session
from ..guest import claim, guest_key
from ..models import Address, Booking, Customer, Order
from ..security import CUSTOMER_COOKIE, hash_password, login_throttle, verify_password
from ..templating import templates
from .order import order_json
from .stol import booking_json

router = APIRouter()

MIN_PASSWORD = 6
MAX_ADDRESSES = 5


def _safe_next(url: str) -> str:
    """Только свои адреса: иначе ссылкой «войти» можно увести гостя на чужой сайт."""
    return url if url.startswith("/") and not url.startswith("//") else "/kabinet"


def _page(request, name, ctx, status=200):
    return templates.TemplateResponse(request, name, {"nav": "kabinet", **ctx}, status_code=status)


async def remember_address(
    session: AsyncSession, customer: Customer, text: str, now: datetime
) -> None:
    """Адрес из заказа — в начало списка гостя; старые сверх лимита забываем."""
    text = text.strip()
    if not text:
        return
    for a in customer.addresses:
        if a.text.lower() == text.lower():
            a.last_used = now
            return
    customer.addresses.append(Address(text=text, last_used=now))
    extra = sorted(customer.addresses, key=lambda a: a.last_used, reverse=True)[MAX_ADDRESSES:]
    for a in extra:
        customer.addresses.remove(a)


# ---------- вход и регистрация ----------


@router.get("/kabinet/vhod", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/kabinet", customer=Depends(current_customer)):
    if customer:
        return RedirectResponse(_safe_next(next), status_code=303)
    return _page(request, "cabinet/login.html", {"next": _safe_next(next), "form": {}, "error": ""})


@router.post("/kabinet/vhod")
async def login(
    request: Request,
    phone: str = Form(""),
    password: str = Form(""),
    next: str = Form("/kabinet"),
    session: AsyncSession = Depends(get_session),
):
    norm = normalize_phone(phone)
    key = f"c:{norm or phone}"
    ctx = {"next": _safe_next(next), "form": {"phone": phone}}
    if login_throttle.blocked(key):
        return _page(
            request,
            "cabinet/login.html",
            {**ctx, "error": "Слишком много попыток. Подождите 15 минут."},
            429,
        )
    customer = (
        await session.scalar(select(Customer).where(Customer.phone == norm)) if norm else None
    )
    if customer is None or not verify_password(password, customer.password_hash):
        login_throttle.fail(key)
        return _page(
            request, "cabinet/login.html", {**ctx, "error": "Неверный телефон или пароль"}, 401
        )
    login_throttle.reset(key)
    # Заказы, сделанные из этого браузера без входа, — сразу в кабинет
    if await claim(session, customer, guest_key(request)):
        await session.commit()
    response = RedirectResponse(_safe_next(next), status_code=303)
    login_customer(response, customer)
    return response


@router.get("/kabinet/registraciya", response_class=HTMLResponse)
async def register_page(
    request: Request, next: str = "/kabinet", customer=Depends(current_customer)
):
    if customer:
        return RedirectResponse("/kabinet", status_code=303)
    return _page(
        request, "cabinet/register.html", {"next": _safe_next(next), "form": {}, "errors": {}}
    )


@router.post("/kabinet/registraciya")
async def register(
    request: Request,
    name: str = Form(""),
    phone: str = Form(""),
    password: str = Form(""),
    next: str = Form("/kabinet"),
    session: AsyncSession = Depends(get_session),
):
    errors = {}
    name = name.strip()
    norm = normalize_phone(phone)
    if not 2 <= len(name) <= 80:
        errors["name"] = "Как к вам обращаться?"
    if norm is None:
        errors["phone"] = PHONE_ERROR
    elif await session.scalar(select(Customer.id).where(Customer.phone == norm)):
        errors["phone"] = "Этот номер уже зарегистрирован — войдите"
    if len(password) < MIN_PASSWORD:
        errors["password"] = f"Пароль — не короче {MIN_PASSWORD} символов"
    if errors:
        ctx = {"next": _safe_next(next), "form": {"name": name, "phone": phone}, "errors": errors}
        return _page(request, "cabinet/register.html", ctx, 422)

    customer = Customer(
        phone=norm, name=name, password_hash=hash_password(password), created_at=lo.now_local()
    )
    session.add(customer)
    await session.flush()
    # Заказы, сделанные из этого браузера до регистрации, — сразу в кабинет
    await claim(session, customer, guest_key(request))
    await session.commit()
    response = RedirectResponse(_safe_next(next), status_code=303)
    login_customer(response, customer)
    return response


@router.post("/kabinet/vyhod")
async def do_logout():
    response = RedirectResponse("/", status_code=303)
    logout(response, CUSTOMER_COOKIE)
    return response


# ---------- кабинет ----------


@router.get("/kabinet", response_class=HTMLResponse)
async def cabinet(
    request: Request,
    customer: Customer = Depends(require_customer),
    session: AsyncSession = Depends(get_session),
):
    orders = (
        await session.scalars(
            select(Order)
            .where(Order.customer_id == customer.id)
            .order_by(Order.id.desc())
            .limit(30)
        )
    ).all()
    active = [o for o in orders if o.status not in ("done", "cancelled")]
    past = [o for o in orders if o.status in ("done", "cancelled")]
    spent = sum(o.total for o in orders if o.status != "cancelled")
    bookings = (
        await session.scalars(
            select(Booking)
            .where(Booking.customer_id == customer.id)
            .order_by(Booking.day.desc(), Booking.time.desc())
            .limit(10)
        )
    ).all()
    return _page(
        request,
        "cabinet/index.html",
        {
            "customer": customer,
            "active": [order_json(o) for o in active],
            "past": [order_json(o) for o in past],
            "bookings": [booking_json(b) for b in bookings],
            "stats": {"count": len([o for o in orders if o.status != "cancelled"]), "spent": spent},
            "saved": request.query_params.get("saved", ""),
        },
    )


@router.post("/kabinet/profil")
async def save_profile(
    name: str = Form(""),
    customer: Customer = Depends(require_customer),
    session: AsyncSession = Depends(get_session),
):
    if 2 <= len(name.strip()) <= 80:
        customer.name = name.strip()
        await session.commit()
    return RedirectResponse("/kabinet?saved=profile#profil", status_code=303)


@router.post("/kabinet/parol")
async def change_password(
    request: Request,
    old: str = Form(""),
    new: str = Form(""),
    customer: Customer = Depends(require_customer),
    session: AsyncSession = Depends(get_session),
):
    if not verify_password(old, customer.password_hash):
        return RedirectResponse("/kabinet?saved=bad-password#profil", status_code=303)
    if len(new) < MIN_PASSWORD:
        return RedirectResponse("/kabinet?saved=short-password#profil", status_code=303)
    customer.password_hash = hash_password(new)
    await session.commit()
    return RedirectResponse("/kabinet?saved=password#profil", status_code=303)


@router.post("/kabinet/adres/{address_id}/udalit")
async def delete_address(
    address_id: int,
    customer: Customer = Depends(require_customer),
    session: AsyncSession = Depends(get_session),
):
    for a in list(customer.addresses):
        if a.id == address_id:
            customer.addresses.remove(a)
    await session.commit()
    return RedirectResponse("/kabinet#adresa", status_code=303)


# ---------- API для экрана заказа ----------


@router.get("/api/me")
async def me(customer: Customer | None = Depends(current_customer)):
    """Экрану заказа: подставить имя, телефон и адреса вошедшего гостя."""
    if customer is None:
        return {"loggedIn": False}
    return {
        "loggedIn": True,
        "name": customer.name,
        "phone": customer.phone,
        "addresses": [a.text for a in customer.addresses],
    }


@router.post("/api/me/claim")
async def claim_orders(
    request: Request,
    customer: Customer | None = Depends(current_customer),
    session: AsyncSession = Depends(get_session),
):
    """Привязать к кабинету заказы и брони, сделанные с этого телефона до входа:
    по ссылкам, запомненным в браузере, и по метке гостя (см. app/guest.py)."""
    if customer is None:
        return JSONResponse({"error": "Нужно войти"}, status_code=401)
    try:
        tokens = (await request.json()).get("tokens", [])
    except (ValueError, AttributeError):
        tokens = []
    moved = await claim(
        session, customer, guest_key(request), tokens if isinstance(tokens, list) else []
    )
    await session.commit()
    return {"claimed": moved}
