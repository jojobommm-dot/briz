"""JSON для Android-приложения: то, что сайт отдаёт внутри HTML-страниц.

Заказы, брони и «мои заказы» приложение берёт из тех же /api/..., что и сайт;
здесь — только витрина (кафе, меню, обеды, банкеты) и данные экрана заказа.
Картинки — относительные пути от корня сайта: приложение само дописывает адрес сервера.
"""

from fastapi import APIRouter

from .. import lunch_order as lo
from ..content import BANQUET_FACTS, BANQUET_PACKAGES, CAFE, LUNCH, MENU

router = APIRouter(prefix="/api/app")


def _image(path: str) -> str:
    return f"/static/img/{path}" if path else ""


@router.get("/content")
async def content():
    return {
        "cafe": {**CAFE, "hours": [{"days": d, "time": t} for d, t in CAFE["hours"]]},
        "menu": [
            {
                "slug": c.slug,
                "title": c.title,
                "dishes": [
                    {
                        "name": d.name,
                        "price": d.price,
                        "weight": d.weight,
                        "note": d.note,
                        "image": _image(d.image),
                    }
                    for d in c.dishes
                ],
            }
            for c in MENU
        ],
        "lunch": {
            "since": LUNCH["since"],
            "prices": [
                {"title": t, "inCafe": cafe, "delivery": dlv} for t, cafe, dlv in LUNCH["prices"]
            ],
            "week": [
                {"day": d, "salad": s, "soup": sp, "main": m, "side": sd}
                for d, s, sp, m, sd in LUNCH["week"]
            ],
        },
        "banquet": {
            "packages": [
                {
                    "slug": p.slug,
                    "title": p.title,
                    "price": p.price,
                    "includes": p.includes,
                    "note": p.note,
                }
                for p in BANQUET_PACKAGES
            ],
            "facts": [{"value": v, "label": label} for v, label in BANQUET_FACTS],
        },
    }


@router.get("/lunch")
async def lunch():
    """Дни, варианты с ценами и свободное время — как у экрана /zakaz на сайте."""
    data = lo.page_data(lo.now_local())
    for day in data["days"]:
        day["image"] = _image(day["image"] or "")
    return data
