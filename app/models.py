"""Таблицы базы."""

from datetime import date, datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Статусы заказа обеда. Порядок — как заказ движется; у доставки и самовывоза
# предпоследний шаг разный
STATUSES = {
    "new": "Новый",
    "accepted": "Принят",
    "cooking": "Готовится",
    "on_way": "Курьер в пути",
    "ready": "Готов к выдаче",
    "done": "Выполнен",
    "cancelled": "Отменён",
}
FLOW = {
    "delivery": ["new", "accepted", "cooking", "on_way", "done"],
    "pickup": ["new", "accepted", "cooking", "ready", "done"],
}


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Ссылка на статус для гостя: /zakaz/<token>. Номер заказа угадать можно, токен — нет
    token: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    created_at: Mapped[datetime]  # местное время Перми
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    mode: Mapped[str] = mapped_column(String(10))  # delivery | pickup
    day: Mapped[date] = mapped_column(index=True)
    slot: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(16))
    address: Mapped[str] = mapped_column(String(200), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    total: Mapped[int]

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OrderItem.id",
    )

    @property
    def status_label(self) -> str:
        return STATUSES.get(self.status, self.status)

    @property
    def flow(self) -> list[str]:
        return FLOW[self.mode]

    @property
    def next_status(self) -> str | None:
        """Следующий шаг для кнопки менеджера; у отменённых и выполненных — нет."""
        if self.status not in self.flow or self.status == "done":
            return None
        return self.flow[self.flow.index(self.status) + 1]


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # full | no_soup | …
    title: Mapped[str] = mapped_column(String(80))
    details: Mapped[str] = mapped_column(String(300), default="")  # блюда этого дня
    qty: Mapped[int]
    price: Mapped[int]  # за штуку, на момент заказа

    order: Mapped[Order] = relationship(back_populates="items")
