from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from pydantic import field_validator
from sqlalchemy import JSON, Integer
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


class OfferStatus(str, Enum):
    complete = "complete"  # every requested line is in the offer
    partial = "partial"  # some lines are missing
    unavailable = "unavailable"  # nothing could be offered
    needs_clarification = "needs_clarification"  # the customer has to answer questions first


class Offer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    customer_email_text: str
    status: OfferStatus
    total: Decimal = Field(sa_type=Money)
    reply_draft: str
    # Suspicious fragments of the e-mail (discount requests, instructions for the AI)
    flags: list[str] = Field(default_factory=list, sa_type=JSON)
    # Questions for the customer about unclear lines; those lines are not guessed
    clarifying_questions: list[str] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime = Field(default_factory=utc_now)


class OfferLine(SQLModel, table=True):
    """One requested line of an offer. item_id is None when the line is missing."""

    id: int | None = Field(default=None, primary_key=True)
    offer_id: int = Field(foreign_key="offer.id", index=True)
    requested: str
    quantity: int
    item_id: int | None = Field(default=None, foreign_key="item.id")
    # Snapshot, so the offer keeps its wording if the product is renamed later
    item_name: str | None = None
    unit_price: Decimal | None = Field(default=None, sa_type=Money)
    is_substitute: bool = False
    # Substitute or budget note for offered lines, the reason for missing lines
    note: str | None = None


class OfferRequest(SQLModel):
    email_text: str = Field(min_length=1, max_length=20000)


class OfferLinePublic(SQLModel):
    item_id: int
    item_name: str
    requested: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    is_substitute: bool
    note: str | None


class OfferMissingPublic(SQLModel):
    requested: str
    quantity: int
    reason: str


class OfferPublic(SQLModel):
    id: int
    status: OfferStatus
    total: Decimal
    lines: list[OfferLinePublic]
    missing: list[OfferMissingPublic]
    flags: list[str]
    clarifying_questions: list[str]
    reply_draft: str
    created_at: datetime

    _utc = field_validator("created_at")(assume_utc)
