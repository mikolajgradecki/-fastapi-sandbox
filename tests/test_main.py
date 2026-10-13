import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def test_db():
    # Each test gets a fresh in-memory database, so tests don't affect each other.
    # StaticPool keeps one connection, otherwise every connection would see its own empty database.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def get_test_session():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[main.get_session] = get_test_session
    yield
    main.app.dependency_overrides.clear()
    engine.dispose()


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_item():
    response = client.post(
        "/items", json={"name": "Laptop", "price": 3999.99, "description": "16 GB RAM"}
    )
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data["id"], int)
    assert data == {
        "id": data["id"],
        "name": "Laptop",
        "price": 3999.99,
        "description": "16 GB RAM",
    }


def test_create_item_without_description():
    response = client.post("/items", json={"name": "Mouse", "price": 49.9})
    assert response.status_code == 201
    assert response.json()["description"] is None


def test_create_item_with_invalid_price():
    response = client.post("/items", json={"name": "Mouse", "price": "abc"})
    assert response.status_code == 422


def test_create_item_missing_required_field():
    response = client.post("/items", json={"name": "Mouse"})
    assert response.status_code == 422


def test_list_items_empty():
    response = client.get("/items")
    assert response.status_code == 200
    assert response.json() == []


def test_list_items():
    client.post("/items", json={"name": "Laptop", "price": 3999.99})
    client.post("/items", json={"name": "Mouse", "price": 49.9})

    response = client.get("/items")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Laptop", "Mouse"]


def test_get_item():
    client.post("/items", json={"name": "Laptop", "price": 3999.99})
    created = client.post("/items", json={"name": "Mouse", "price": 49.9}).json()

    response = client.get(f"/items/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


@pytest.mark.parametrize("item_id", [0, 5, -1])
def test_get_item_not_found(item_id):
    response = client.get(f"/items/{item_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found"}


def create_laptop():
    response = client.post(
        "/items", json={"name": "Laptop", "price": 3999.99, "description": "16 GB RAM"}
    )
    return response.json()


def test_replace_item():
    item = create_laptop()

    response = client.put(f"/items/{item['id']}", json={"name": "Tablet", "price": 1999.0})
    assert response.status_code == 200
    # PUT replaces the whole item, so the omitted description is cleared
    assert response.json() == {
        "id": item["id"],
        "name": "Tablet",
        "price": 1999.0,
        "description": None,
    }
    assert client.get(f"/items/{item['id']}").json() == response.json()


def test_replace_item_not_found():
    response = client.put("/items/999", json={"name": "Tablet", "price": 1999.0})
    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found"}


def test_update_item():
    item = create_laptop()

    response = client.patch(f"/items/{item['id']}", json={"price": 3499.0})
    assert response.status_code == 200
    # PATCH changes only the sent field, the rest stays as it was
    assert response.json() == {**item, "price": 3499.0}
    assert client.get(f"/items/{item['id']}").json() == response.json()


def test_update_item_clears_description():
    item = create_laptop()

    response = client.patch(f"/items/{item['id']}", json={"description": None})
    assert response.status_code == 200
    assert response.json() == {**item, "description": None}


def test_update_item_not_found():
    response = client.patch("/items/999", json={"price": 3499.0})
    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found"}


@pytest.mark.parametrize("field", ["name", "price"])
def test_update_item_rejects_null(field):
    item = create_laptop()

    response = client.patch(f"/items/{item['id']}", json={field: None})
    assert response.status_code == 422
    assert client.get(f"/items/{item['id']}").json() == item


def test_delete_item():
    item = create_laptop()

    response = client.delete(f"/items/{item['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_delete_item_not_found():
    response = client.delete("/items/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found"}


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Mouse", "price": -10},
        {"name": "Mouse", "price": 0},
        {"name": "", "price": 49.9},
        {"name": "x" * 101, "price": 49.9},
    ],
)
def test_create_item_invalid(payload):
    response = client.post("/items", json=payload)
    assert response.status_code == 422


def test_create_item_name_max_length():
    response = client.post("/items", json={"name": "x" * 100, "price": 49.9})
    assert response.status_code == 201


def test_replace_item_with_negative_price():
    item = create_laptop()

    response = client.put(f"/items/{item['id']}", json={"name": "Laptop", "price": -1})
    assert response.status_code == 422


def test_update_item_with_negative_price():
    item = create_laptop()

    response = client.patch(f"/items/{item['id']}", json={"price": -1})
    assert response.status_code == 422
    assert client.get(f"/items/{item['id']}").json() == item


def engine_url_for(env):
    # main reads DATABASE_URL at import time, so check it in a fresh Python process
    result = subprocess.run(
        [sys.executable, "-c", "import main; print(main.engine.url)"],
        cwd=Path(__file__).parent.parent,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_database_url_default():
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    assert engine_url_for(env) == "sqlite:///database.db"


def test_database_url_from_env():
    env = {**os.environ, "DATABASE_URL": "sqlite:///other.db"}
    assert engine_url_for(env) == "sqlite:///other.db"


def create_numbered_items(count):
    for number in range(1, count + 1):
        client.post("/items", json={"name": f"Item {number}", "price": number})


def names(response):
    return [item["name"] for item in response.json()]


def test_list_items_default_limit():
    create_numbered_items(25)

    response = client.get("/items")
    assert response.status_code == 200
    assert names(response) == [f"Item {number}" for number in range(1, 21)]


def test_list_items_offset_and_limit():
    create_numbered_items(10)

    response = client.get("/items", params={"offset": 3, "limit": 4})
    assert response.status_code == 200
    assert names(response) == ["Item 4", "Item 5", "Item 6", "Item 7"]


def test_list_items_offset_past_end():
    create_numbered_items(3)

    response = client.get("/items", params={"offset": 10})
    assert response.status_code == 200
    assert response.json() == []


def test_list_items_max_limit():
    create_numbered_items(101)

    response = client.get("/items", params={"limit": 100})
    assert response.status_code == 200
    assert len(response.json()) == 100


@pytest.mark.parametrize(
    "params", [{"offset": -1}, {"limit": 0}, {"limit": 101}, {"limit": "abc"}]
)
def test_list_items_invalid_pagination(params):
    response = client.get("/items", params=params)
    assert response.status_code == 422


@pytest.fixture
def shop_items():
    for name, price in [
        ("Gaming Laptop", 5999.0),
        ("Office laptop", 2499.0),
        ("Mouse", 49.9),
        ("100% cotton pad", 19.9),
    ]:
        client.post("/items", json={"name": name, "price": price})


@pytest.mark.usefixtures("shop_items")
@pytest.mark.parametrize(
    "params, expected",
    [
        ({"name": "laptop"}, ["Gaming Laptop", "Office laptop"]),
        ({"name": "LAPTOP"}, ["Gaming Laptop", "Office laptop"]),
        ({"name": "use"}, ["Mouse"]),
        ({"name": "%"}, ["100% cotton pad"]),
        ({"name": "_"}, []),
        ({"name": "tablet"}, []),
        ({"min_price": 2499}, ["Gaming Laptop", "Office laptop"]),
        ({"max_price": 49.9}, ["Mouse", "100% cotton pad"]),
        ({"min_price": 20, "max_price": 3000}, ["Office laptop", "Mouse"]),
        ({"name": "laptop", "max_price": 3000}, ["Office laptop"]),
        ({"name": "laptop", "limit": 1, "offset": 1}, ["Office laptop"]),
    ],
)
def test_search_items(params, expected):
    response = client.get("/items", params=params)
    assert response.status_code == 200
    assert names(response) == expected


def test_search_min_price_greater_than_max_price():
    response = client.get("/items", params={"min_price": 100, "max_price": 10})
    assert response.status_code == 422
    assert response.json() == {"detail": "min_price cannot be greater than max_price"}


@pytest.mark.parametrize("params", [{"min_price": -1}, {"max_price": "abc"}])
def test_search_invalid_price_filter(params):
    response = client.get("/items", params=params)
    assert response.status_code == 422
