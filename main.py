import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import field_validator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Field, Session, SQLModel, col, create_engine, select


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
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///database.db"

# check_same_thread=False: FastAPI runs sync endpoints in a thread pool (SQLite only)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(lifespan=lifespan)


def get_item_or_404(session: Session, item_id: int) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/health")
def health(session: SessionDep, response: Response):
    try:
        session.exec(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return {"status": "error", "database": "unavailable"}
    return {"status": "ok", "database": "ok"}


@app.post("/items", status_code=201, response_model=ItemPublic)
def create_item(item: ItemCreate, session: SessionDep):
    now = utc_now()
    db_item = Item.model_validate(item, update={"created_at": now, "updated_at": now})
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.get("/items", response_model=list[ItemPublic])
def list_items(
    session: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    name: str | None = None,
    min_price: Annotated[float | None, Query(ge=0)] = None,
    max_price: Annotated[float | None, Query(ge=0)] = None,
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=422, detail="min_price cannot be greater than max_price"
        )

    statement = select(Item)
    if name:
        # autoescape: % and _ in the search text are matched literally, not as wildcards
        statement = statement.where(col(Item.name).icontains(name, autoescape=True))
    if min_price is not None:
        statement = statement.where(Item.price >= min_price)
    if max_price is not None:
        statement = statement.where(Item.price <= max_price)

    statement = statement.order_by(Item.id).offset(offset).limit(limit)
    return session.exec(statement).all()


@app.get("/items/{item_id}", response_model=ItemPublic)
def get_item(item_id: int, session: SessionDep):
    return get_item_or_404(session, item_id)


@app.put("/items/{item_id}", response_model=ItemPublic)
def replace_item(item_id: int, item: ItemCreate, session: SessionDep):
    db_item = get_item_or_404(session, item_id)
    # Full dump: fields left out of the request go back to their defaults
    db_item.sqlmodel_update(item.model_dump(), update={"updated_at": utc_now()})
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.patch("/items/{item_id}", response_model=ItemPublic)
def update_item(item_id: int, item: ItemUpdate, session: SessionDep):
    db_item = get_item_or_404(session, item_id)
    db_item.sqlmodel_update(
        item.model_dump(exclude_unset=True), update={"updated_at": utc_now()}
    )
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, session: SessionDep):
    db_item = get_item_or_404(session, item_id)
    session.delete(db_item)
    session.commit()
