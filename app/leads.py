"""Заявки на банкет и кейтеринг: сохранение с сайта в базу и лента для менеджера."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .banquet import BanquetRequest
from .catering import CateringRequest
from .content import BANQUET_PACKAGES, CATERING_FORMATS
from .lunch_order import now_local
from .models import LEAD_OPEN, Lead

# (вид, slug) → «Праздник», «Фуршет»: в базе хранится slug, менеджеру — название
OPTION_TITLES = {("banquet", p.slug): p.title for p in BANQUET_PACKAGES} | {
    ("catering", f.slug): f.title for f in CATERING_FORMATS
}
CLOSED_SHOWN = 30


async def save(session: AsyncSession, req: BanquetRequest | CateringRequest) -> Lead:
    if isinstance(req, BanquetRequest):
        kind, option, place = "banquet", req.package, ""
    else:
        kind, option, place = "catering", req.format, req.place
    lead = Lead(
        kind=kind,
        created_at=now_local(),
        name=req.name,
        phone=req.phone,
        event_date=date.fromisoformat(req.event_date),
        guests=req.guests,
        option=option,
        place=place,
        comment=req.comment,
    )
    session.add(lead)
    await session.commit()
    return lead


async def board(session: AsyncSession) -> tuple[list[Lead], list[Lead]]:
    """Открытые (сначала новые, дальше по дате праздника) и последние закрытые."""
    open_ = (await session.scalars(select(Lead).where(Lead.status.in_(LEAD_OPEN)))).all()
    closed = (
        await session.scalars(
            select(Lead)
            .where(Lead.status.not_in(LEAD_OPEN))
            .order_by(Lead.id.desc())
            .limit(CLOSED_SHOWN)
        )
    ).all()
    return sorted(open_, key=lambda x: (x.status != "new", x.event_date, x.id)), list(closed)
