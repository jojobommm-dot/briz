"""Рабочее место менеджера: заказы обедов на день, статусы, сводка для кухни.

Вход — HTTP Basic (логин и пароль из .env: MANAGE_USER, MANAGE_PASSWORD).
Нормальные учётки сотрудников появятся вместе с админкой; пока менеджер один.
"""

import secrets
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import lunch_order as lo
from ..config import settings
from ..database import get_session
from ..models import STATUSES, Order
from ..templating import templates

# В заголовках HTTP только латиница — realm без кириллицы
basic = HTTPBasic(realm="briz")


def manager(creds: HTTPBasicCredentials = Depends(basic)) -> str:
    if not settings.manage_password:
        raise HTTPException(503, "Панель выключена: задайте MANAGE_PASSWORD в .env")
    ok_user = secrets.compare_digest(creds.username.encode(), settings.manage_user.encode())
    ok_pass = secrets.compare_digest(creds.password.encode(), settings.manage_password.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(401, headers={"WWW-Authenticate": 'Basic realm="briz"'})
    return creds.username


router = APIRouter(prefix="/manage", dependencies=[Depends(manager)])


@router.get("")
async def manage_root():
    return RedirectResponse("/manage/zakazy", status_code=303)


@router.get("/zakazy", response_class=HTMLResponse)
async def orders(request: Request, day: str = "", session: AsyncSession = Depends(get_session)):
    today = lo.now_local().date()
    try:
        chosen = date.fromisoformat(day) if day else today
    except ValueError:
        chosen = today

    rows = (
        await session.scalars(select(Order).where(Order.day == chosen).order_by(Order.id.desc()))
    ).all()
    active = [o for o in rows if o.status != "cancelled"]

    # Сводка для кухни: сколько каких блюд готовить на день
    kitchen = Counter()
    for o in active:
        for it in o.items:
            for part in lo.OPTIONS_BY_KIND[it.kind].parts if it.kind in lo.OPTIONS_BY_KIND else ():
                kitchen[part] += it.qty
    menu = lo.menu_for(chosen) or {}

    return templates.TemplateResponse(
        request,
        "manage/orders.html",
        {
            "orders": rows,
            "day": chosen,
            "today": today,
            "days": [d["date"] for d in lo.order_days(lo.now_local())],
            "kitchen": [
                (menu.get(p, p), kitchen[p], label)
                for p, label in (("salad", "Салат"), ("soup", "Суп"), ("main", "Второе"))
            ],  # fmt: skip
            "revenue": sum(o.total for o in active),
            "counts": Counter(o.status for o in rows),
            "statuses": STATUSES,
            "max_id": max((o.id for o in rows), default=0),
            "modes": lo.MODES,
        },
    )


@router.post("/zakazy/{order_id}/status")
async def set_status(order_id: int, status: str = Form(...), day: str = Form(""),
                     session: AsyncSession = Depends(get_session)):  # fmt: skip
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(404)
    if status not in STATUSES or (status != "cancelled" and status not in order.flow):
        raise HTTPException(400)
    order.status = status
    await session.commit()
    return RedirectResponse(
        f"/manage/zakazy?day={day or order.day.isoformat()}#o{order.id}", status_code=303
    )


@router.get("/api/latest")
async def latest(session: AsyncSession = Depends(get_session)):
    """Для опроса со страницы: номер последнего заказа и сколько новых."""
    max_id = await session.scalar(select(func.max(Order.id))) or 0
    new = await session.scalar(select(func.count()).select_from(Order).where(Order.status == "new"))
    return {"maxId": max_id, "new": new}
