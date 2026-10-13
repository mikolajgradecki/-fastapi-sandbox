from datetime import datetime, timezone

from pydantic import field_validator
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ItemBase(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    price: float = Field(gt=0)
    description: str | None = None


class Item(ItemBase, table=True):
    # The database assigns the id, so it is None until the item is saved
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ItemCreate(ItemBase):
    pass


class ItemPublic(ItemBase):
    id: int
    created_at: datetime
    updated_at: datetime

    # SQLite drops the time zone when it stores a datetime; all stored times are UTC
    @field_validator("created_at", "updated_at")
    @classmethod
    def assume_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class ItemUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    price: float | None = Field(default=None, gt=0)
    description: str | None = None

    # Omitting name or price is fine, but an explicit null would break the NOT NULL column
    @field_validator("name", "price")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("cannot be null")
        return value


# "or" also covers DATABASE_URL set to an empty string
