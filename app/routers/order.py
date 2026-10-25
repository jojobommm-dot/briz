"""Приложение для гостей: заказ обедов, его статус и правка, «мои заказы»."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import lunch_order as lo
from ..auth import current_customer
from ..content import LUNCH
from ..database import get_session
from ..guest import ensure_guest, guest_key
from ..models import STATUSES, Booking, Customer, Order, OrderItem
from ..templating import templates

router = APIRouter()
log = logging.getLogger("briz.order")


def can_edit(o: Order, now: datetime) -> bool:
    """Гость меняет заказ сам, пока менеджер не принял и приём на этот день открыт."""
    return o.status == "new" and lo.is_open(o.day, o.mode, now)


def order_json(o: Order) -> dict:
    return {
        "number": o.id,
        "token": o.token,
        "status": o.status,
        "statusLabel": o.status_label,
        "flow": [{"key": s, "label": STATUSES[s]} for s in o.flow],
        "mode": o.mode,
        "modeLabel": lo.MODES[o.mode],
        "day": o.day.isoformat(),
        "dayLabel": f"{lo.WEEKDAYS[o.day.weekday()]}, {o.day.day} {lo.MONTHS[o.day.month - 1]}",
        "slot": o.slot,
        "address": o.address,
        "guests": o.guests,
        "name": o.name,
        "phone": o.phone,
        "comment": o.comment,
        "total": o.total,
        "items": [
            {"kind": i.kind, "title": i.title, "details": i.details, "qty": i.qty, "price": i.price}
            for i in o.items
        ],
        "canCancel": o.status == "new",
        "canEdit": can_edit(o, lo.now_local()),
        "editedAt": o.edited_at.strftime("%H:%M") if o.edited_at else "",
    }


def _items(draft: lo.OrderDraft) -> list[OrderItem]:
    return [
        OrderItem(
            kind=o.kind,
            title=o.title,
            details=lo.details(o, draft.day),
            qty=qty,
            price=lo.price(o, draft.mode),
        )
        for o, qty in draft.items
    ]


async def _payload(request: Request) -> dict | None:
    try:
        payload = await request.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


async def _by_token(token: str, session: AsyncSession) -> Order:
    order = await session.scalar(select(Order).where(Order.token == token))
    if order is None:
        raise HTTPException(404)
    return order


@router.get("/zakaz", response_class=HTMLResponse)
async def order_page(request: Request):
    return templates.TemplateResponse(
        request,
        "order.html",
        {"data": lo.page_data(lo.now_local()), "lunch": LUNCH, "nav": "zakaz"},
    )


@router.post("/api/orders")
async def create_order(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    customer: Customer | None = Depends(current_customer),
):
    payload = await _payload(request)
    if payload is None:
        return JSONResponse({"errors": {"form": "Пустой заказ"}}, status_code=422)

    now = lo.now_local()
    draft, errors = lo.validate(payload, now)
    if draft is None:
        return JSONResponse({"errors": errors}, status_code=422)

    order = Order(
        token=lo.new_token(),
        created_at=now,
        status="new",
        mode=draft.mode,
        day=draft.day,
        slot=draft.slot,
        name=draft.name,
        phone=draft.phone,
        address=draft.address,
        comment=draft.comment,
        total=draft.total,
        guests=draft.guests,
        # Метку ставим и вошедшим: выйдет из кабинета — заказы на этом телефоне останутся видны
        guest_key=ensure_guest(request, response),
        items=_items(draft),
    )
    if customer is not None:
        # Заказ — в историю кабинета, адрес — в сохранённые
        order.customer_id = customer.id
        if draft.mode == "delivery":
            from .cabinet import remember_address

            await remember_address(session, customer, draft.address, now)
    session.add(order)
    await session.commit()
    log.info("Заказ обеда №%s: %s, %s, %s ₽", order.id, order.day, order.mode, order.total)
    return {"token": order.token, "url": f"/zakaz/{order.token}", "order": order_json(order)}


@router.put("/api/orders/{token}")
async def edit_order(
    token: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    customer: Customer | None = Depends(current_customer),
):
    """Гость меняет свой заказ вместо того, чтобы оформлять второй: состав, способ,
    день, время, адрес. Только пока заказ «Новый» и приём открыт."""
    order = await _by_token(token, session)
    now = lo.now_local()
    if not can_edit(order, now):
        return JSONResponse(
            {"errors": {"form": "Заказ уже в работе — изменить можно по телефону"}}, status_code=409
        )
    payload = await _payload(request)
    if payload is None:
        return JSONResponse({"errors": {"form": "Пустой заказ"}}, status_code=422)
    draft, errors = lo.validate(payload, now)
    if draft is None:
        return JSONResponse({"errors": errors}, status_code=422)

    for field in ("mode", "day", "slot", "name", "phone", "address", "comment", "guests"):
        setattr(order, field, getattr(draft, field))
    order.items = _items(draft)
    order.total = draft.total
    order.edited_at = now
    order.guest_key = order.guest_key or ensure_guest(request, response)
    if customer is not None and draft.mode == "delivery":
        from .cabinet import remember_address

        await remember_address(session, customer, draft.address, now)
    await session.commit()
    log.info("Заказ обеда №%s изменён: %s, %s, %s ₽", order.id, order.day, order.mode, order.total)
    return {"token": order.token, "url": f"/zakaz/{order.token}", "order": order_json(order)}


@router.get("/api/my")
async def my_orders(
    request: Request,
    tokens: str = "",
    session: AsyncSession = Depends(get_session),
    customer: Customer | None = Depends(current_customer),
):
    """Активные заказы и брони этого гостя — на сегодня и вперёд, пока не закрыты.
    Свои — по кабинету, по метке браузера или по ссылкам, запомненным на телефоне
    (заказы, сделанные до появления метки)."""
    from .stol import booking_json

    key = guest_key(request)
    known = [t for t in tokens.split(",") if t][:20]
    today = lo.now_local().date()
    found = {}
    for model in (Order, Booking):
        mine = []
        if customer is not None:
            mine.append(model.customer_id == customer.id)
        if key:
            mine.append(model.guest_key == key)
        if known:
            mine.append(model.token.in_(known))
        if not mine:
            found[model] = []
            continue
        found[model] = (
            await session.scalars(
                select(model)
                .where(or_(*mine), model.day >= today, model.status.not_in(("done", "cancelled")))
                .order_by(model.day, model.id)
                .limit(20)
            )
        ).all()
    return {
        "orders": [order_json(o) for o in found[Order]],
        "bookings": [booking_json(b) for b in found[Booking]],
    }


@router.get("/api/orders/{token}")
async def order_status(token: str, session: AsyncSession = Depends(get_session)):
    return order_json(await _by_token(token, session))


@router.post("/api/orders/{token}/cancel")
async def cancel_order(token: str, session: AsyncSession = Depends(get_session)):
    order = await _by_token(token, session)
    # Гость отменяет сам, пока менеджер не принял; дальше — только звонком
    if order.status != "new":
        return JSONResponse({"error": "Заказ уже в работе — позвоните в кафе"}, status_code=409)
    order.status = "cancelled"
    await session.commit()
    return order_json(order)


@router.get("/zakaz/{token}", response_class=HTMLResponse)
async def order_status_page(
    request: Request, token: str, session: AsyncSession = Depends(get_session)
):
    order = await _by_token(token, session)
    return templates.TemplateResponse(
        request, "order_status.html", {"order": order_json(order), "nav": "zakaz"}
    )
