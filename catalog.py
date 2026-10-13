"""Catalog queries shared by the /items endpoints and the AI agent tools."""

from fastapi import HTTPException
from sqlmodel import Session, col, select

from models import Item


def search_items(
    session: Session,
    *,
    name: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[Item]:
    statement = select(Item)
    if name:
        # autoescape: % and _ in the search text are matched literally, not as wildcards
        statement = statement.where(col(Item.name).icontains(name, autoescape=True))
    if min_price is not None:
        statement = statement.where(Item.price >= min_price)
    if max_price is not None:
        statement = statement.where(Item.price <= max_price)

    statement = statement.order_by(Item.id).offset(offset).limit(limit)
    return list(session.exec(statement).all())


def get_item_or_404(session: Session, item_id: int) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
