import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def clear_items():
    # Each test starts with an empty list, so tests don't affect each other
    main.items.clear()
    yield
    main.items.clear()


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
    assert response.json() == {
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
    client.post("/items", json={"name": "Mouse", "price": 49.9})

    response = client.get("/items/1")
    assert response.status_code == 200
    assert response.json()["name"] == "Mouse"


@pytest.mark.parametrize("item_id", [0, 5, -1])
def test_get_item_not_found(item_id):
    response = client.get(f"/items/{item_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found"}
