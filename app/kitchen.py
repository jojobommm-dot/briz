"""Лист для кухни: что и сколько готовить на день по заказам обедов.

Из каждого заказанного варианта («Полный комплекс», «Суп и второе»…) получаем
блюда дня: салат, суп, второе и гарнир (второе всегда идёт с гарниром). Дальше:
- сколько порций каждого блюда и сколько это в граммах по нормам выхода;
- к какому времени: по слотам доставки и самовывоза;
- сколько уже отдано (курьер уехал / забрали / выполнен) и сколько осталось;
- упаковка: контейнеры, приборы, пакеты.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from . import lunch_order as lo
from .content import LUNCH
from .models import Order

PARTS = [("salad", "Салат"), ("soup", "Суп"), ("main", "Второе"), ("side", "Гарнир")]
# Из чего состоит вариант: второе всегда с гарниром
EXPAND = {"salad": ("salad",), "soup": ("soup",), "main": ("main", "side")}
SENT = {"on_way", "ready", "done"}  # с кухни уже ушло


def slot_start(slot: str) -> str:
    """«12:30–13:00» → «12:30»: к этому времени блюдо должно быть готово."""
    return slot.split("–")[0]


def parts_of(kind: str) -> list[str]:
    option = lo.OPTIONS_BY_KIND.get(kind)
    if option is None:
        return []
    return [p for part in option.parts for p in EXPAND[part]]


@dataclass
class DishRow:
    part: str
    label: str
    dish: str
    total: int = 0
    sent: int = 0
    delivery: int = 0
    pickup: int = 0
    by_time: Counter = field(default_factory=Counter)
    portion: int = 0
    unit: str = ""

    @property
    def left(self) -> int:
        return self.total - self.sent

    @property
    def amount(self) -> str:
        """Общий выход: 2 400 г → «2,4 кг», 3 750 мл → «3,75 л»."""
        value = self.total * self.portion
        if value >= 1000:
            big = {"г": "кг", "мл": "л"}[self.unit]
            return f"{value / 1000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + f" {big}"
        return f"{value} {self.unit}"


@dataclass
class Sheet:
    day: date
    rows: list[DishRow]
    times: list[str]
    combos: list[dict]  # «Полный комплекс × 5 → салат, суп, второе, гарнир»
    packaging: dict
    orders: int
    waiting: int  # новых, ещё не принятых


def build(orders: list[Order], day: date) -> Sheet:
    dishes = lo.dishes_for(day) or {}
    active = [o for o in orders if o.status != "cancelled"]
    rows = {
        part: DishRow(
            part,
            label,
            dishes.get(part, "—"),
            portion=LUNCH["portions"][part][0],
            unit=LUNCH["portions"][part][1],
        )
        for part, label in PARTS
    }
    combos: dict[str, Counter] = defaultdict(Counter)
    times: set[str] = set()
    containers = Counter()
    cutlery = 0

    for o in active:
        t = slot_start(o.slot)
        times.add(t)
        for it in o.items:
            parts = parts_of(it.kind)
            combos[it.title]["qty"] += it.qty
            combos[it.title]["mode_" + o.mode] += it.qty
            for p in parts:
                r = rows[p]
                r.total += it.qty
                r.by_time[t] += it.qty
                setattr(r, o.mode, getattr(r, o.mode) + it.qty)
                if o.status in SENT:
                    r.sent += it.qty
            # Контейнеры: суп — свой, салат — свой, второе с гарниром — в одном
            for p in parts:
                if p in ("salad", "soup", "main"):
                    containers[p] += it.qty
            if "soup" in parts or "main" in parts:
                cutlery += it.qty

    combo_rows = []
    for option in lo.OPTIONS:
        c = combos.get(option.title)
        if not c:
            continue
        combo_rows.append(
            {
                "title": option.title,
                "qty": c["qty"],
                "delivery": c["mode_delivery"],
                "pickup": c["mode_pickup"],
                "parts": [dict(PARTS)[p] for p in parts_of(option.kind)],
                "dishes": [dishes.get(p, "—") for p in parts_of(option.kind)],
            }
        )

    return Sheet(
        day=day,
        rows=list(rows.values()),
        times=sorted(times),
        combos=combo_rows,
        packaging={
            "soup": containers["soup"],
            "salad": containers["salad"],
            "main": containers["main"],
            "cutlery": cutlery,
            "bags": len(active),
        },
        orders=len(active),
        waiting=sum(1 for o in active if o.status == "new"),
    )
