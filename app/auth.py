"""Кто зашёл: гость с кабинетом и сотрудник. Зависимости для роутеров."""

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import get_session
from .models import Customer, Staff
from .security import (
    CUSTOMER_COOKIE,
    CUSTOMER_DAYS,
    STAFF_COOKIE,
    STAFF_DAYS,
    make_session,
    read_session,
)


class LoginRequired(Exception):
    """Страница только для вошедших — main.py отправит на вход и вернёт обратно."""

    def __init__(self, login_url: str, next_url: str):
        self.login_url, self.next_url = login_url, next_url


def _cookie(response: Response, name: str, value: str, days: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.base_url.startswith("https"),
    )


def login_customer(response: Response, customer: Customer) -> None:
    _cookie(response, CUSTOMER_COOKIE, make_session("c", customer.id), CUSTOMER_DAYS)


def login_staff(response: Response, staff: Staff) -> None:
    _cookie(response, STAFF_COOKIE, make_session("s", staff.id), STAFF_DAYS)


def logout(response: Response, name: str) -> None:
    response.delete_cookie(name)


async def current_customer(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Customer | None:
    cid = read_session(request.cookies.get(CUSTOMER_COOKIE), "c", CUSTOMER_DAYS)
    return await session.get(Customer, cid) if cid else None


async def require_customer(
    request: Request, customer: Customer | None = Depends(current_customer)
) -> Customer:
    if customer is None:
        raise LoginRequired("/kabinet/vhod", request.url.path)
    return customer


async def current_staff(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Staff | None:
    sid = read_session(request.cookies.get(STAFF_COOKIE), "s", STAFF_DAYS)
    staff = await session.get(Staff, sid) if sid else None
    return staff if staff and staff.is_active else None


async def require_staff(request: Request, staff: Staff | None = Depends(current_staff)) -> Staff:
    if staff is None:
        raise LoginRequired(
            "/manage/vhod",
            str(request.url.path) + (f"?{request.url.query}" if request.url.query else ""),
        )
    return staff
