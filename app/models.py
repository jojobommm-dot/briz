"""Таблицы базы."""

from datetime import date, datetime

from sqlalchemy import ForeignKey, String, Text, desc
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


class Customer(Base):
    """Гость с личным кабинетом. Вход по телефону и паролю."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(16), unique=True, index=True)  # +7XXXXXXXXXX
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime]

    addresses: Mapped[list["Address"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by=lambda: desc(Address.last_used),
    )


class Address(Base):
    """Адреса доставки гостя: последний использованный — первым."""

    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(String(200))
    last_used: Mapped[datetime]

    customer: Mapped[Customer] = relationship(back_populates="addresses")


class Staff(Base):
    """Сотрудник кафе с доступом к /manage."""

    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16), default="manager")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime]


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
    # Заказ гостя с кабинетом; заказы без входа — None
    # Mapped[int] + nullable, а не Mapped[int | None]: SQLAlchemy 2.0.36 на Python 3.14
    # не разбирает объединения типов в аннотациях
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), index=True, nullable=True, default=None
    )

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


# Заявки на банкет и кейтеринг: менеджер перезванивает и ведёт до договорённости
LEAD_KINDS = {"banquet": "Банкет", "catering": "Кейтеринг"}
LEAD_STATUSES = {
    "new": "Новая",
    "in_work": "В работе",
    "done": "Договорились",
    "declined": "Отказ",
}
LEAD_OPEN = ("new", "in_work")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10), index=True)  # banquet | catering
    created_at: Mapped[datetime]  # местное время Перми
    status: Mapped[str] = mapped_column(String(10), default="new", index=True)
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(16))
    event_date: Mapped[date]
    guests: Mapped[int]
    option: Mapped[str] = mapped_column(String(20))  # пакет банкета или формат кейтеринга
    place: Mapped[str] = mapped_column(String(200), default="")  # куда везти кейтеринг
    comment: Mapped[str] = mapped_column(Text, default="")

    @property
    def status_label(self) -> str:
        return LEAD_STATUSES.get(self.status, self.status)

    @property
    def kind_label(self) -> str:
        return LEAD_KINDS.get(self.kind, self.kind)
