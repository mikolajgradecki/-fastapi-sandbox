from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import SQLModel

import ai
import offers
import ui
from catalog import get_item_or_404, search_items
from database import SessionDep, engine
from models import (
    Item,
    ItemCreate,
    ItemPublic,
    ItemUpdate,
    Offer,
    OfferPublic,
    OfferRejection,
    OfferRequest,
    utc_now,
)


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


def ai_client():
    # Dependencies run before body validation, so a missing key must not fail here:
    # a bad request still gets 422, and the config error comes out when the model is used
    try:
        return ai.get_client()
    except ai.AIConfigError as error:
        return ai.UnavailableProvider(str(error))


AIClientDep = Annotated[object, Depends(ai_client)]

app.include_router(ui.build_router(ai_client))
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.post("/offers/from-email", status_code=201, response_model=OfferPublic)
def create_offer_from_email(request: OfferRequest, session: SessionDep, llm: AIClientDep):
    try:
        offer = offers.process_email(llm, session, request.email_text)
    except ai.AIConfigError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ai.AIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return offers.offer_public(session, offer)


def get_offer_or_404(session, offer_id: int) -> Offer:
    offer = session.get(Offer, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    return offer


@app.get("/offers/{offer_id}", response_model=OfferPublic)
def get_offer(offer_id: int, session: SessionDep):
    return offers.offer_public(session, get_offer_or_404(session, offer_id))


def decide_offer(session, offer_id: int, approve: bool, reason: str | None = None):
    offer = get_offer_or_404(session, offer_id)
    try:
        offer = offers.decide(session, offer, approve, reason)
    except offers.OfferAlreadyDecided as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return offers.offer_public(session, offer)


@app.post("/offers/{offer_id}/approve", response_model=OfferPublic)
def approve_offer(offer_id: int, session: SessionDep):
    return decide_offer(session, offer_id, approve=True)


@app.post("/offers/{offer_id}/reject", response_model=OfferPublic)
def reject_offer(offer_id: int, rejection: OfferRejection, session: SessionDep):
    return decide_offer(session, offer_id, approve=False, reason=rejection.reason)
