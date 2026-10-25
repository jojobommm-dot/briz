"""Кабинет менеджера: заказы на день, лист для кухни, лист выдачи, брони столов, заявки
на банкет и кейтеринг.

Вход — по логину и паролю сотрудника (таблица staff). Первый менеджер
создаётся при запуске из MANAGE_USER/MANAGE_PASSWORD, остальные — tools/staff.py.
"""

from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import booking as bk
from .. import kitchen, leads
from .. import lunch_order as lo
from ..auth import current_staff, login_staff, logout, require_staff
from ..database import get_session
from ..models import (
    BOOKING_FLOW,
    BOOKING_STATUSES,
    LEAD_STATUSES,
    STATUSES,
    Booking,
    Lead,
    Order,
    Staff,
)
from ..security import STAFF_COOKIE, login_throttle, verify_password
from ..templating import templates

public = APIRouter(prefix="/manage")
router = APIRouter(prefix="/manage")


def _safe_next(url: str) -> str:
    return url if url.startswith("/manage") else "/manage/zakazy"


def _pick_day(day: str) -> tuple[date, date]:
    today = lo.now_local().date()
    try:
        return (date.fromisoformat(day) if day else today), today
    except ValueError:
        return today, today


async def _orders_for(session: AsyncSession, day: date) -> list[Order]:
    return list(
        (
            await session.scalars(select(Order).where(Order.day == day).order_by(Order.id.desc()))
        ).all()
    )


async def _live(session: AsyncSession) -> dict:
    """Для шапки и опроса: последние номера заказа и заявки по всей базе, сколько новых
    заявок. Номера — общие, а не за выбранный день: иначе на дне без свежего заказа
    опрос считал бы его новым и перезагружал страницу каждые 15 секунд."""
    return {
        "max_id": await session.scalar(select(func.max(Order.id))) or 0,
        "max_lead": await session.scalar(select(func.max(Lead.id))) or 0,
        "max_booking": await session.scalar(select(func.max(Booking.id))) or 0,
        # Гость изменил заказ или бронь — страница тоже должна позвать
        "last_edit": max(
            (
                str(t)
                for t in (
                    await session.scalar(select(func.max(Order.edited_at))),
                    await session.scalar(select(func.max(Booking.edited_at))),
                )
                if t
            ),
            default="",
        ),
        "new_leads": await session.scalar(
            select(func.count()).select_from(Lead).where(Lead.status == "new")
        ),
    }


def _ctx(staff: Staff, tab: str, day: date, today: date, **extra) -> dict:
    return {
        "tab": tab,
        "day": day,
        "today": today,
        "days": [d["date"] for d in lo.order_days(lo.now_local())],
        "staff": staff,
        "statuses": STATUSES,
        "modes": lo.MODES,
        **extra,
    }


# ---------- вход ----------


@public.get("/vhod", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/manage/zakazy", staff=Depends(current_staff)):
    if staff:
        return RedirectResponse(_safe_next(next), status_code=303)
    return templates.TemplateResponse(
        request, "manage/login.html", {"next": _safe_next(next), "error": "", "login": ""}
    )


@public.post("/vhod")
async def login(
    request: Request,
    login: str = Form(""),
    password: str = Form(""),
    next: str = Form("/manage/zakazy"),
    session: AsyncSession = Depends(get_session),
):
    key = f"s:{login.strip().lower()}"
    ctx = {"next": _safe_next(next), "login": login}
    if login_throttle.blocked(key):
        ctx["error"] = "Слишком много попыток. Подождите 15 минут."
        return templates.TemplateResponse(request, "manage/login.html", ctx, status_code=429)
    staff = await session.scalar(select(Staff).where(Staff.login == login.strip().lower()))
    if staff is None or not staff.is_active or not verify_password(password, staff.password_hash):
        login_throttle.fail(key)
        ctx["error"] = "Неверный логин или пароль"
        return templates.TemplateResponse(request, "manage/login.html", ctx, status_code=401)
    login_throttle.reset(key)
    response = RedirectResponse(_safe_next(next), status_code=303)
    login_staff(response, staff)
    return response


@public.post("/vyhod")
async def do_logout():
    response = RedirectResponse("/manage/vhod", status_code=303)
    logout(response, STAFF_COOKIE)
    return response


# ---------- разделы ----------


@router.get("")
async def manage_root(staff: Staff = Depends(require_staff)):
    return RedirectResponse("/manage/zakazy", status_code=303)


@router.get("/zakazy", response_class=HTMLResponse)
async def orders(
    request: Request,
    day: str = "",
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    chosen, today = _pick_day(day)
    rows = await _orders_for(session, chosen)
    active = [o for o in rows if o.status != "cancelled"]
    return templates.TemplateResponse(
        request,
        "manage/orders.html",
        _ctx(
            staff,
            "zakazy",
            chosen,
            today,
            orders=rows,
            sheet=kitchen.build(rows, chosen),
            revenue=sum(o.total for o in active),
            counts=Counter(o.status for o in rows),
            **await _live(session),
        ),
    )


@router.get("/kuhnya", response_class=HTMLResponse)
async def kitchen_page(
    request: Request,
    day: str = "",
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    chosen, today = _pick_day(day)
    rows = await _orders_for(session, chosen)
    return templates.TemplateResponse(
        request,
        "manage/kitchen.html",
        _ctx(
            staff,
            "kuhnya",
            chosen,
            today,
            sheet=kitchen.build(rows, chosen),
            **await _live(session),
        ),  # fmt: skip
    )


@router.get("/dostavka")
async def delivery_old(day: str = ""):
    """Старый адрес вкладки — закладки и ярлыки менеджеров продолжают работать."""
    return RedirectResponse(f"/manage/vydacha?day={day}" if day else "/manage/vydacha", 307)


@router.get("/vydacha", response_class=HTMLResponse)
async def handout_page(
    request: Request,
    day: str = "",
    mode: str = "",
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    """Лист выдачи: все заказы дня по времени — курьеру, на стойку самовывоза и в зал.
    Фильтр mode оставляет один способ: например, распечатать маршрут курьеру."""
    chosen, today = _pick_day(day)
    active = [o for o in await _orders_for(session, chosen) if o.status != "cancelled"]
    mode = mode if mode in lo.MODES else ""
    rows = [o for o in active if not mode or o.mode == mode]
    order_of = list(lo.MODES)  # курьер уезжает раньше, чем гость заходит в зал
    rows.sort(key=lambda o: (kitchen.slot_start(o.slot), order_of.index(o.mode), o.id))
    groups: dict[str, list[Order]] = {}
    for o in rows:
        groups.setdefault(kitchen.slot_start(o.slot), []).append(o)
    by_mode = {
        m: {
            "count": sum(1 for o in active if o.mode == m),
            "left": sum(1 for o in active if o.mode == m and o.status != "done"),
        }
        for m in lo.MODES
    }
    return templates.TemplateResponse(
        request,
        "manage/handout.html",
        _ctx(
            staff,
            "vydacha",
            chosen,
            today,
            groups=groups,
            mode=mode,
            by_mode=by_mode,
            to_collect=sum(o.total for o in rows if o.status != "done"),
            **await _live(session),
        ),  # fmt: skip
    )


@router.post("/zakazy/{order_id}/status")
async def set_status(
    order_id: int,
    status: str = Form(...),
    back: str = Form(""),
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(404)
    if status not in STATUSES or (status != "cancelled" and status not in order.flow):
        raise HTTPException(400)
    order.status = status
    await session.commit()
    target = back if back.startswith("/manage/") else f"/manage/zakazy?day={order.day.isoformat()}"
    return RedirectResponse(f"{target}#o{order.id}", status_code=303)


@router.get("/stoly", response_class=HTMLResponse)
async def bookings_page(
    request: Request,
    day: str = "",
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    """Брони столов на день: кто, во сколько, сколько гостей, что подать к приходу."""
    chosen, today = _pick_day(day)
    rows = list(
        (
            await session.scalars(
                select(Booking).where(Booking.day == chosen).order_by(Booking.time, Booking.id)
            )
        ).all()
    )
    active = [b for b in rows if b.status != "cancelled"]
    # Кухне: предзаказ по блюдам и ко времени
    pre: dict[str, dict] = {}
    for b in active:
        for it in b.items:
            row = pre.setdefault(it.name, {"category": it.category, "qty": 0, "by_time": Counter()})
            row["qty"] += it.qty
            row["by_time"][b.time] += it.qty
    upcoming = [(today + timedelta(days=i)).isoformat() for i in range(bk.DAYS_AHEAD)]
    return templates.TemplateResponse(
        request,
        "manage/bookings.html",
        _ctx(
            staff,
            "stoly",
            chosen,
            today,
            days=upcoming,
            bookings=rows,
            pre=sorted(pre.items(), key=lambda kv: (kv[1]["category"], kv[0])),
            guests=sum(b.guests for b in active),
            pre_total=sum(b.total for b in active),
            waiting=sum(1 for b in active if b.status == "new"),
            booking_statuses=BOOKING_STATUSES,
            count=len(active),
            **await _live(session),
        ),  # fmt: skip
    )


@router.post("/stoly/{booking_id}/status")
async def set_booking_status(
    booking_id: int,
    status: str = Form(...),
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(404)
    if status not in BOOKING_FLOW and status != "cancelled":
        raise HTTPException(400)
    booking.status = status
    await session.commit()
    return RedirectResponse(
        f"/manage/stoly?day={booking.day.isoformat()}#b{booking.id}", status_code=303
    )


@router.get("/zayavki", response_class=HTMLResponse)
async def leads_page(
    request: Request,
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    today = lo.now_local().date()
    open_, closed = await leads.board(session)
    return templates.TemplateResponse(
        request,
        "manage/leads.html",
        _ctx(
            staff,
            "zayavki",
            today,
            today,
            open=open_,
            closed=closed,
            lead_statuses=LEAD_STATUSES,
            option_titles=leads.OPTION_TITLES,
            weekdays=lo.WEEKDAYS,
            **await _live(session),
        ),
    )


@router.post("/zayavki/{lead_id}/status")
async def set_lead_status(
    lead_id: int,
    status: str = Form(...),
    staff: Staff = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    lead = await session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404)
    if status not in LEAD_STATUSES:
        raise HTTPException(400)
    lead.status = status
    await session.commit()
    return RedirectResponse(f"/manage/zayavki#z{lead.id}", status_code=303)


@router.get("/api/latest")
async def latest(
    staff: Staff = Depends(require_staff), session: AsyncSession = Depends(get_session)
):
    """Для опроса со страницы: последние номера заказа и заявки, сколько новых заказов."""
    live = await _live(session)
    new = await session.scalar(select(func.count()).select_from(Order).where(Order.status == "new"))
    return {
        "maxId": live["max_id"],
        "maxLead": live["max_lead"],
        "maxBooking": live["max_booking"],
        "lastEdit": live["last_edit"],
        "new": new,
    }
