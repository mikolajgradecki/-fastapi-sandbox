from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import SQLModel

from catalog import get_item_or_404, search_items
from database import SessionDep, engine
from models import Item, ItemCreate, ItemPublic, ItemUpdate, utc_now


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(lifespan=lifespan)


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
    category: str | None = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=422, detail="min_price cannot be greater than max_price"
        )
    return search_items(
        session,
        name=name,
        category=category,
        min_price=min_price,
        max_price=max_price,
        offset=offset,
        limit=limit,
    )


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
