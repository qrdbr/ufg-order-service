import pytest
from fastapi.testclient import TestClient

from app import repository
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state():
    repository.reset()


def make_order(items=None, coupon=None):
    payload = {
        "customer_email": "cliente@example.com",
        "items": items if items is not None else [{"product_id": 1, "quantity": 2}],
    }
    if coupon:
        payload["coupon"] = coupon
    return client.post("/orders", json=payload)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_list_products():
    response = client.get("/products")
    assert response.status_code == 200
    assert len(response.json()) == 4


def test_create_order_calculates_total_and_reserves_stock():
    response = make_order()
    assert response.status_code == 201
    body = response.json()
    assert body["subtotal"] == 699.80
    assert body["total"] == 699.80
    assert body["status"] == "PENDING"
    assert repository.products[1].stock == 8


def test_create_order_with_coupon():
    body = make_order(coupon="PROMO10").json()
    assert body["discount"] == 69.98
    assert body["total"] == 629.82


def test_create_order_without_items_fails():
    assert make_order(items=[]).status_code == 400


def test_create_order_unknown_product():
    assert make_order(items=[{"product_id": 999, "quantity": 1}]).status_code == 404


def test_create_order_out_of_stock():
    assert make_order(items=[{"product_id": 4, "quantity": 1}]).status_code == 409


def test_get_order():
    order_id = make_order().json()["id"]
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["id"] == order_id


def test_get_unknown_order():
    assert client.get("/orders/123").status_code == 404


def test_pay_order():
    order_id = make_order().json()["id"]
    response = client.post(f"/orders/{order_id}/pay")
    assert response.json()["status"] == "PAID"
    assert client.post(f"/orders/{order_id}/pay").status_code == 409


def test_cancel_order_returns_stock():
    order_id = make_order().json()["id"]
    response = client.post(f"/orders/{order_id}/cancel")
    assert response.json()["status"] == "CANCELLED"
    assert repository.products[1].stock == 10


def test_metrics_endpoint():
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "orderservice_http_requests_total" in response.text
