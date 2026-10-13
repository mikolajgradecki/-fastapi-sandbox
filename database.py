import os
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, create_engine

# "or" also covers DATABASE_URL set to an empty string
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///database.db"

# check_same_thread=False: FastAPI runs sync endpoints in a thread pool (SQLite only)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
