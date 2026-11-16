from enum import StrEnum

from pydantic import BaseModel


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"


class Product(BaseModel):
    id: int
    name: str
    price: float
    stock: int


class OrderItemIn(BaseModel):
    product_id: int
    quantity: int


class OrderIn(BaseModel):
    customer_email: str
    items: list[OrderItemIn]
    coupon: str | None = None


class OrderItem(BaseModel):
    product_id: int
    quantity: int
    unit_price: float


class Order(BaseModel):
    id: int
    customer_email: str
    items: list[OrderItem]
    subtotal: float
    discount: float
    total: float
    status: OrderStatus
