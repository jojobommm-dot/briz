"""Приложение для гостей: заказ обедов и статус заказа."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import lunch_order as lo
from ..auth import current_customer
from ..database import get_session
from ..models import STATUSES, Customer, Order, OrderItem
from ..templating import templates

router = APIRouter()
log = logging.getLogger("briz.order")


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
        "total": o.total,
        "items": [
            {"kind": i.kind, "title": i.title, "details": i.details, "qty": i.qty, "price": i.price}
            for i in o.items
        ],
        "canCancel": o.status == "new",
    }


async def _by_token(token: str, session: AsyncSession) -> Order:
    order = await session.scalar(select(Order).where(Order.token == token))
    if order is None:
        raise HTTPException(404)
    return order


@router.get("/zakaz", response_class=HTMLResponse)
async def order_page(request: Request):
    return templates.TemplateResponse(
        request, "order.html", {"data": lo.page_data(lo.now_local()), "nav": "zakaz"}
    )


@router.post("/api/orders")
async def create_order(
    request: Request,
    session: AsyncSession = Depends(get_session),
    customer: Customer | None = Depends(current_customer),
):
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
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
        items=[
            OrderItem(
                kind=o.kind,
                title=o.title,
                details=lo.details(o, draft.day),
                qty=qty,
                price=lo.price(o, draft.mode),
            )
            for o, qty in draft.items
        ],
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
