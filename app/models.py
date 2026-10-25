"""Таблицы базы."""

from datetime import date, datetime

from sqlalchemy import ForeignKey, String, Text, desc
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Статусы заказа обеда. Порядок — как заказ движется; у доставки, самовывоза
# и обеда в зале предпоследний шаг свой
STATUSES = {
    "new": "Новый",
    "accepted": "Принят",
    "cooking": "Готовится",
    "on_way": "Курьер в пути",
    "ready": "Готов к выдаче",
    "served": "Стол накрыт",
    "done": "Выполнен",
    "cancelled": "Отменён",
}
FLOW = {
    "delivery": ["new", "accepted", "cooking", "on_way", "done"],
    "pickup": ["new", "accepted", "cooking", "ready", "done"],
    "hall": ["new", "accepted", "cooking", "served", "done"],
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
    mode: Mapped[str] = mapped_column(String(10))  # delivery | pickup | hall
    day: Mapped[date] = mapped_column(index=True)
    slot: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(16))
    address: Mapped[str] = mapped_column(String(200), default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    total: Mapped[int]
    guests: Mapped[int] = mapped_column(default=0)  # обед в зале: на сколько человек стол
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


# Бронь стола: менеджер подтверждает, отмечает, что гости пришли; гость может
# отменить сам, пока не пришёл
BOOKING_STATUSES = {
    "new": "Новая",
    "confirmed": "Стол подтверждён",
    "seated": "Гости пришли",
    "done": "Завершена",
    "cancelled": "Отменена",
}
BOOKING_FLOW = ["new", "confirmed", "seated", "done"]


class Booking(Base):
    """Стол ко времени: бронь с предзаказом из основного меню (app/booking.py)."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(24), unique=True, index=True)  # /stol/<token>
    created_at: Mapped[datetime]  # местное время Перми
    status: Mapped[str] = mapped_column(String(12), default="new", index=True)
    day: Mapped[date] = mapped_column(index=True)
    time: Mapped[str] = mapped_column(String(5))  # «18:30»
    guests: Mapped[int]
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str] = mapped_column(Text, default="")
    total: Mapped[int] = mapped_column(default=0)  # предзаказ; без него — 0
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), index=True, nullable=True, default=None
    )

    items: Mapped[list["BookingItem"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BookingItem.id",
    )

    @property
    def status_label(self) -> str:
        return BOOKING_STATUSES.get(self.status, self.status)

    @property
    def next_status(self) -> str | None:
        if self.status not in BOOKING_FLOW or self.status == "done":
            return None
        return BOOKING_FLOW[BOOKING_FLOW.index(self.status) + 1]


class BookingItem(Base):
    __tablename__ = "booking_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(160))  # раздел/название — см. booking.dish_key
    category: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    qty: Mapped[int]
    price: Mapped[int]  # за штуку, на момент брони

    booking: Mapped[Booking] = relationship(back_populates="items")
