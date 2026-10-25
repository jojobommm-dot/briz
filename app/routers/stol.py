"""Стол ко времени: бронь с предзаказом и её статус для гостя."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import booking as bk
from .. import lunch_order as lo
from ..auth import current_customer
from ..database import get_session
from ..guest import ensure_guest
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
        "name": b.name,
        "phone": b.phone,
        "comment": b.comment,
        "total": b.total,
        "items": [
            {"key": i.key, "category": i.category, "name": i.name, "qty": i.qty, "price": i.price}
            for i in b.items
        ],
        "canCancel": b.status in bk.GUEST_CAN_CANCEL,
        "canEdit": bk.can_edit(b.status, b.day, b.time, lo.now_local()),
        "editedAt": b.edited_at.strftime("%H:%M") if b.edited_at else "",
    }


def _items(draft: bk.BookingDraft) -> list[BookingItem]:
    return [
        BookingItem(key=key, category=cat, name=d.name, qty=qty, price=d.price)
        for key, cat, d, qty in draft.items
    ]


async def _payload(request: Request) -> dict | None:
    try:
        payload = await request.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


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
    response: Response,
    session: AsyncSession = Depends(get_session),
    customer: Customer | None = Depends(current_customer),
):
    payload = await _payload(request)
    if payload is None:
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
        guest_key=ensure_guest(request, response),
        items=_items(draft),
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


@router.put("/api/bookings/{token}")
async def edit_booking(
    token: str,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Гость меняет бронь: день, время, гостей, предзаказ. Подтверждённая бронь после
    правки снова ждёт подтверждения менеджера — время или число гостей могли измениться."""
    booking = await _by_token(token, session)
    now = lo.now_local()
    if not bk.can_edit(booking.status, booking.day, booking.time, now):
        return JSONResponse(
            {"errors": {"form": "Бронь уже не изменить онлайн — позвоните в кафе"}}, status_code=409
        )
    payload = await _payload(request)
    if payload is None:
        return JSONResponse({"errors": {"form": "Пустая заявка"}}, status_code=422)
    draft, errors = bk.validate(payload, now)
    if draft is None:
        return JSONResponse({"errors": errors}, status_code=422)

    for field in ("day", "time", "guests", "name", "phone", "comment"):
        setattr(booking, field, getattr(draft, field))
    booking.items = _items(draft)
    booking.total = draft.total
    booking.status = "new"
    booking.edited_at = now
    booking.guest_key = booking.guest_key or ensure_guest(request, response)
    await session.commit()
    log.info(
        "Бронь стола №%s изменена: %s %s, %s чел.",
        booking.id,
        booking.day,
        booking.time,
        booking.guests,
    )
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
