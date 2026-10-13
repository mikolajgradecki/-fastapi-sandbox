import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import database
import main


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    # .env and system variables may hold real keys; no test may reach a paid API
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    for name in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "GEMINI_MODEL", "ANTHROPIC_MODEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def db_engine():
    # A fresh in-memory database for every test, so tests don't affect each other.
    # StaticPool keeps one connection, otherwise every connection would see its own empty database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def test_db(db_engine):
    def get_test_session():
        with Session(db_engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = get_test_session
    yield
    main.app.dependency_overrides.clear()
