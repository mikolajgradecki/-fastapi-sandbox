from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import field_validator
from sqlmodel import Field, Session, SQLModel, create_engine, select


class ItemBase(SQLModel):
    name: str = Field(min_length=1, max_length=100)
    price: float = Field(gt=0)
    description: str | None = None


class Item(ItemBase, table=True):
    # The database assigns the id, so it is None until the item is saved
    id: int | None = Field(default=None, primary_key=True)


class ItemCreate(ItemBase):
    pass


class ItemPublic(ItemBase):
    id: int


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


# check_same_thread=False: FastAPI runs sync endpoints in a thread pool
engine = create_engine(
    "sqlite:///database.db", connect_args={"check_same_thread": False}
)


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
async def health():
    return {"status": "ok"}


@app.post("/items", status_code=201, response_model=ItemPublic)
def create_item(item: ItemCreate, session: SessionDep):
    db_item = Item.model_validate(item)
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.get("/items", response_model=list[ItemPublic])
def list_items(session: SessionDep):
    return session.exec(select(Item).order_by(Item.id)).all()


@app.get("/items/{item_id}", response_model=ItemPublic)
def get_item(item_id: int, session: SessionDep):
    return get_item_or_404(session, item_id)


@app.put("/items/{item_id}", response_model=ItemPublic)
def replace_item(item_id: int, item: ItemCreate, session: SessionDep):
    db_item = get_item_or_404(session, item_id)
    # Full dump: fields left out of the request go back to their defaults
    db_item.sqlmodel_update(item.model_dump())
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.patch("/items/{item_id}", response_model=ItemPublic)
def update_item(item_id: int, item: ItemUpdate, session: SessionDep):
    db_item = get_item_or_404(session, item_id)
    db_item.sqlmodel_update(item.model_dump(exclude_unset=True))
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


@app.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, session: SessionDep):
    db_item = get_item_or_404(session, item_id)
    session.delete(db_item)
    session.commit()
