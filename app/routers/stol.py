"""Стол ко времени: бронь с предзаказом и её статус для гостя."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import booking as bk
from .. import lunch_order as lo
from ..auth import current_customer
from ..database import get_session
from ..models import BOOKING_FLOW, BOOKING_STATUSES, Booking, BookingItem, Customer
from ..templating import templates

router = APIRouter()
log = logging.getLogger("briz.stol")


def booking_json(b: Booking) -> dict:
    return {
        "number": b.id,
        "token": b.token,
        "status": b.status,
        "statusLabel": b.status_label,
        "flow": [{"key": s, "label": BOOKING_STATUSES[s]} for s in BOOKING_FLOW],
        "day": b.day.isoformat(),
        "dayLabel": f"{lo.WEEKDAYS[b.day.weekday()]}, {b.day.day} {lo.MONTHS[b.day.month - 1]}",
        "time": b.time,
        "guests": b.guests,
        "comment": b.comment,
        "total": b.total,
        "items": [
            {"key": i.key, "category": i.category, "name": i.name, "qty": i.qty, "price": i.price}
            for i in b.items
        ],
        "canCancel": b.status in bk.GUEST_CAN_CANCEL,
    }


async def _by_token(token: str, session: AsyncSession) -> Booking:
    booking = await session.scalar(select(Booking).where(Booking.token == token))
    if booking is None:
        raise HTTPException(404)
    return booking


@router.get("/stol", response_class=HTMLResponse)
async def booking_page(request: Request):
    return templates.TemplateResponse(
        request, "stol.html", {"data": bk.page_data(lo.now_local()), "nav": "stol"}
    )


@router.post("/api/bookings")
async def create_booking(
    request: Request,
    session: AsyncSession = Depends(get_session),
    customer: Customer | None = Depends(current_customer),
):
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return JSONResponse({"errors": {"form": "Пустая заявка"}}, status_code=422)

    now = lo.now_local()
    draft, errors = bk.validate(payload, now)
    if draft is None:
        return JSONResponse({"errors": errors}, status_code=422)

    booking = Booking(
        token=lo.new_token(),
        created_at=now,
        status="new",
        day=draft.day,
        time=draft.time,
        guests=draft.guests,
        name=draft.name,
        phone=draft.phone,
        comment=draft.comment,
        total=draft.total,
        customer_id=customer.id if customer else None,
        items=[
            BookingItem(key=key, category=cat, name=d.name, qty=qty, price=d.price)
            for key, cat, d, qty in draft.items
        ],
    )
    session.add(booking)
    await session.commit()
    log.info("Бронь стола №%s: %s %s, %s чел., предзаказ %s ₽",
             booking.id, booking.day, booking.time, booking.guests, booking.total)  # fmt: skip
    return {
        "token": booking.token,
        "url": f"/stol/{booking.token}",
        "booking": booking_json(booking),
    }


@router.get("/api/bookings/{token}")
async def booking_status(token: str, session: AsyncSession = Depends(get_session)):
    return booking_json(await _by_token(token, session))


@router.post("/api/bookings/{token}/cancel")
async def cancel_booking(token: str, session: AsyncSession = Depends(get_session)):
    booking = await _by_token(token, session)
    if booking.status not in bk.GUEST_CAN_CANCEL:
        return JSONResponse({"error": "Бронь уже не отменить — позвоните в кафе"}, status_code=409)
    booking.status = "cancelled"
    await session.commit()
    return booking_json(booking)


@router.get("/stol/{token}", response_class=HTMLResponse)
async def booking_status_page(
    request: Request, token: str, session: AsyncSession = Depends(get_session)
):
    booking = await _by_token(token, session)
    return templates.TemplateResponse(
        request, "stol_status.html", {"booking": booking_json(booking), "nav": "stol"}
    )
