"""JSON для рабочих вкладок Android-приложения — то же, что /manage, но данными.

Вход — та же кука сотрудника, что у сайта (briz_staff): приложение хранит её у себя
и продлевает при каждом открытии рабочих вкладок (/me) — кто заходит хотя бы раз
в две недели, пароль заново не вводит. Без входа — 401 (main.py на всё под /api/
отвечает JSON-ом).

Вкладка — один запрос со всем для экрана; смена статуса возвращает обновлённую
карточку. Подписи (статусы, способы, даты) — готовые, по-русски: приложение их
только показывает. Расчёты — те же функции, что у страниц менеджера (manage.py).
"""

from datetime import date

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import kitchen, leads
from .. import lunch_order as lo
from ..auth import login_staff, logout, require_staff
from ..content import CAFE
from ..database import get_session
from ..models import BOOKING_STATUSES, STATUSES, Booking, Lead, Order, Staff
from ..security import STAFF_COOKIE
from . import manage

router = APIRouter(prefix="/api/app/staff")


async def _payload(request: Request) -> dict:
    try:
        payload = await request.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _me(staff: Staff) -> dict:
    return {"name": staff.name, "login": staff.login, "role": staff.role}


def _days(chosen: date, today: date, dates: list[str]) -> list[dict]:
    """Полоса дней над вкладкой; выбранный день, которого в ней нет, — тоже в ней."""
    days = sorted({date.fromisoformat(d) for d in dates} | {chosen})
    return [
        {
            "date": d.isoformat(),
            "label": lo.day_label(d, today),
            "short": f"{lo.WEEKDAYS[d.weekday()]}, {d.day} {lo.MONTHS[d.month - 1]}",
        }
        for d in days
    ]


def _lunch_days(chosen: date, today: date) -> list[dict]:
    """Дни обедов: сегодня и пять рабочих вперёд — как на сайте."""
    return _days(chosen, today, [d["date"] for d in lo.order_days(lo.now_local())])


def _order(o: Order) -> dict:
    nxt = o.next_status
    return {
        "id": o.id,
        "status": o.status,
        "statusLabel": o.status_label,
        "next": nxt,
        "nextLabel": STATUSES[nxt] if nxt else None,
        "canCancel": o.status not in ("done", "cancelled"),
        "mode": o.mode,
        "modeLabel": lo.MODES[o.mode],
        "slot": o.slot,
        "created": o.created_at.strftime("%H:%M"),
        "edited": o.edited_at.strftime("%H:%M") if o.edited_at else None,
        "cabinet": o.customer_id is not None,
        "name": o.name,
        "phone": o.phone,
        "address": o.address,
        "comment": o.comment,
        "guests": o.guests,
        "total": o.total,
        "items": [{"qty": i.qty, "title": i.title, "details": i.details} for i in o.items],
    }


def _booking(b: Booking) -> dict:
    nxt = b.next_status
    return {
        "id": b.id,
        "time": b.time,
        "status": b.status,
        "statusLabel": b.status_label,
        "next": nxt,
        "nextLabel": BOOKING_STATUSES[nxt] if nxt else None,
        "canCancel": b.status not in ("done", "cancelled"),
        "guests": b.guests,
        "created": b.created_at.strftime("%d.%m %H:%M"),
        "edited": b.edited_at.strftime("%d.%m в %H:%M") if b.edited_at else None,
        "cabinet": b.customer_id is not None,
        "name": b.name,
        "phone": b.phone,
        "comment": b.comment,
        "total": b.total,
        "items": [{"qty": i.qty, "name": i.name, "category": i.category} for i in b.items],
    }


def _lead(x: Lead) -> dict:
    d = x.event_date
    return {
        "id": x.id,
        "kindLabel": x.kind_label,
        "status": x.status,
        "statusLabel": x.status_label,
        "created": x.created_at.strftime("%d.%m %H:%M"),
        "event": f"{lo.WEEKDAYS[d.weekday()]}, {d.strftime('%d.%m.%Y')}",
        "guests": leads.guests_label(x.guests),
        "option": leads.OPTION_TITLES.get((x.kind, x.option), x.option),
        "name": x.name,
        "phone": x.phone,
        "place": x.place,
        "comment": x.comment,
        "actions": leads.actions(x),
    }


# ---------- вход ----------


@router.post("/login")
async def login(request: Request, session: AsyncSession = Depends(get_session)):
    body = await _payload(request)
    staff, error, code = await manage.authenticate(
        session, str(body.get("login", "")), str(body.get("password", ""))
    )
    if staff is None:
        return JSONResponse({"error": error}, status_code=code)
    response = JSONResponse(_me(staff))
    login_staff(response, staff)
    return response


@router.post("/logout")
async def do_logout():
    response = JSONResponse({"ok": True})
    logout(response, STAFF_COOKIE)
    return response


@router.get("/me")
async def me(response: Response, staff: Staff = Depends(require_staff)):
    """Кто вошёл; заодно продлевает вход ещё на две недели."""
    login_staff(response, staff)
    return _me(staff)


@router.get("/latest")
async def latest(
    staff: Staff = Depends(require_staff), session: AsyncSession = Depends(get_session)
):
    """Опрос раз в 15 секунд: пришло ли новое (звук) и сколько ждёт ответа (значки вкладок)."""
    now = await manage.live(session)

    async def waiting(model) -> int:
        return await session.scalar(
            select(func.count()).select_from(model).where(model.status == "new")
        )

    return {
        "maxId": now["max_id"],
        "maxLead": now["max_lead"],
        "maxBooking": now["max_booking"],
        "lastEdit": now["last_edit"],
        "newOrders": await waiting(Order),
        "newBookings": await waiting(Booking),
        "newLeads": now["new_leads"],
    }


# ---------- вкладки ----------


@router.get("/orders")
async def orders(
    day: str = "",
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    """«Заказы»: заказы дня, сколько ждут ответа, сумма, сколько каждого блюда ещё отдать."""
    chosen, today = manage.pick_day(day)
    rows = await manage.orders_for(session, chosen)
    sheet = kitchen.build(rows, chosen)
    return {
        "day": chosen.isoformat(),
        "days": _lunch_days(chosen, today),
        "count": sheet.orders,
        "waiting": sheet.waiting,
        "revenue": sum(o.total for o in rows if o.status != "cancelled"),
        "dishes": [{"label": r.label, "dish": r.dish, "left": r.left} for r in sheet.rows],
        "orders": [_order(o) for o in rows],
    }


@router.get("/kitchen")
async def kitchen_sheet(
    day: str = "",
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    """«Кухня»: что и сколько готовить, к какому времени, из чего складываются заказы."""
    chosen, today = manage.pick_day(day)
    sheet = kitchen.build(await manage.orders_for(session, chosen), chosen)
    return {
        "day": chosen.isoformat(),
        "days": _lunch_days(chosen, today),
        "count": sheet.orders,
        "waiting": sheet.waiting,
        "times": sheet.times,
        "dishes": [
            {
                "label": r.label,
                "dish": r.dish,
                "total": r.total,
                "left": r.left,
                "sent": r.sent,
                "amount": r.amount,
                "portion": f"{r.portion} {r.unit}",
                "delivery": r.delivery,
                "pickup": r.pickup,
                "hall": r.hall,
                "byTime": [r.by_time[t] for t in sheet.times],  # по порядку times
            }
            for r in sheet.rows
        ],
        "combos": sheet.combos,
        "hall": {
            "tables": sheet.hall["tables"],
            "guests": sheet.hall["guests"],
            "byTime": [{"time": t, "tables": n} for t, n in sorted(sheet.hall["by_time"].items())],
        },
        "packaging": sheet.packaging,
    }


@router.get("/handout")
async def handout_sheet(
    day: str = "",
    mode: str = "",
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    """«Выдача»: заказы по времени — курьеру, на стойку и в зал; сколько получить с гостей."""
    chosen, today = manage.pick_day(day)
    active = [o for o in await manage.orders_for(session, chosen) if o.status != "cancelled"]
    mode = mode if mode in lo.MODES else ""
    sheet = manage.handout(active, mode)
    by_mode = sheet["by_mode"]
    every = {
        "count": sum(m["count"] for m in by_mode.values()),
        "left": sum(m["left"] for m in by_mode.values()),
    }
    return {
        "day": chosen.isoformat(),
        "days": _lunch_days(chosen, today),
        "mode": mode,
        "modes": [{"mode": "", "label": "Все", **every}]
        + [{"mode": m, "label": label, **by_mode[m]} for m, label in lo.MODES.items()],
        "toCollect": sheet["to_collect"],
        "groups": [
            {"time": t, "orders": [_order(o) for o in rows]} for t, rows in sheet["groups"].items()
        ],
    }


@router.get("/bookings")
async def bookings(
    day: str = "",
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    """«Столы»: брони дня и предзаказ кухне ко времени прихода."""
    chosen, today = manage.pick_day(day)
    rows = await manage.bookings_for(session, chosen)
    t = manage.tables(rows)
    return {
        "day": chosen.isoformat(),
        "days": _days(chosen, today, manage.upcoming(today)),
        "count": t["count"],
        "waiting": t["waiting"],
        "guests": t["guests"],
        "capacity": CAFE["capacity"],
        "preTotal": t["pre_total"],
        "pre": [
            {
                "name": name,
                "category": r["category"],
                "qty": r["qty"],
                "byTime": [{"time": tm, "qty": q} for tm, q in sorted(r["by_time"].items())],
            }
            for name, r in t["pre"]
        ],
        "bookings": [_booking(b) for b in rows],
    }


@router.get("/leads")
async def lead_board(
    staff: Staff = Depends(require_staff), session: AsyncSession = Depends(get_session)
):
    """«Заявки»: открытые — новые сверху, дальше по дате праздника; последние закрытые."""
    open_, closed = await leads.board(session)
    return {"open": [_lead(x) for x in open_], "closed": [_lead(x) for x in closed]}


# ---------- статусы ----------


@router.post("/orders/{order_id}/status")
async def order_status(
    order_id: int,
    request: Request,
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    status = str((await _payload(request)).get("status", ""))
    return _order(await manage.change_order(session, order_id, status))


@router.post("/bookings/{booking_id}/status")
async def booking_status(
    booking_id: int,
    request: Request,
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    status = str((await _payload(request)).get("status", ""))
    return _booking(await manage.change_booking(session, booking_id, status))


@router.post("/leads/{lead_id}/status")
async def lead_status(
    lead_id: int,
    request: Request,
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    status = str((await _payload(request)).get("status", ""))
    return _lead(await manage.change_lead(session, lead_id, status))
