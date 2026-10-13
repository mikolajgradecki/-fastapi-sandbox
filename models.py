from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from pydantic import field_validator
from sqlalchemy import Integer
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel

CENT = Decimal("0.01")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


class Money(TypeDecorator):
    """Stores Decimal amounts as whole grosze (Integer).

    SQLite has no exact decimal type: Numeric would be stored as a float and could round.
    """

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return int(to_money(value) * 100)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return to_money(Decimal(value) / 100)


def normalize_category(value: str) -> str:
    return value.strip().lower()


class ItemBase(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2, sa_type=Money)
    description: str | None = None
    category: str = Field(default="inne", min_length=1, max_length=50)
    stock: int = Field(default=0, ge=0)

    @field_validator("category")
    @classmethod
    def lowercase_category(cls, value: str) -> str:
        return normalize_category(value)


class Item(ItemBase, table=True):
    # The database assigns the id, so it is None until the item is saved
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ItemCreate(ItemBase):
    pass


def assume_utc(value: datetime) -> datetime:
    # SQLite drops the time zone when it stores a datetime; all stored times are UTC
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class ItemPublic(ItemBase):
    id: int
    created_at: datetime
    updated_at: datetime

    _utc = field_validator("created_at", "updated_at")(assume_utc)


class ItemUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    description: str | None = None
    category: str | None = Field(default=None, min_length=1, max_length=50)
    stock: int | None = Field(default=None, ge=0)

    # Omitting these fields is fine, but an explicit null would break the NOT NULL column
    @field_validator("name", "price", "category", "stock")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("cannot be null")
        return value

    @field_validator("category")
    @classmethod
    def lowercase_category(cls, value: str) -> str:
        return normalize_category(value)
