"""Catalog queries shared by the /items endpoints and the AI agent tools."""

from decimal import Decimal

from fastapi import HTTPException
from sqlmodel import Session, col, select

from models import Item, normalize_category


def search_items(
    session: Session,
    *,
    name: str | None = None,
    category: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[Item]:
    statement = select(Item)
    # Every word must appear somewhere in the name, so "dell 27" finds "Monitor Dell P2725H 27"
    for word in (name or "").split():
        # autoescape: % and _ in the search text are matched literally, not as wildcards
        statement = statement.where(col(Item.name).icontains(word, autoescape=True))
    if category:
        statement = statement.where(Item.category == normalize_category(category))
    if min_price is not None:
        statement = statement.where(Item.price >= min_price)
    if max_price is not None:
        statement = statement.where(Item.price <= max_price)

    statement = statement.order_by(Item.id).offset(offset).limit(limit)
    return list(session.exec(statement).all())


def list_categories(session: Session) -> list[str]:
    return list(session.exec(select(Item.category).distinct().order_by(Item.category)).all())


def get_item_or_404(session: Session, item_id: int) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
