"""Armazenamento em memória.

FRÁGIL (intencional): dicionários globais mutáveis, sem lock e sem transação.
Requisições concorrentes podem gerar IDs duplicados ou estoque negativo.
"""

from app.models import Order, Product

_SEED_PRODUCTS = [
    Product(id=1, name="Teclado mecânico", price=349.90, stock=10),
    Product(id=2, name="Mouse sem fio", price=129.90, stock=25),
    Product(id=3, name="Monitor 27\"", price=1899.00, stock=5),
    Product(id=4, name="Headset", price=259.99, stock=0),
]

products: dict[int, Product] = {}
orders: dict[int, Order] = {}
_next_order_id = 1


def reset() -> None:
    global _next_order_id
    products.clear()
    orders.clear()
    for p in _SEED_PRODUCTS:
        products[p.id] = p.model_copy()
    _next_order_id = 1


def next_order_id() -> int:
    global _next_order_id
    current = _next_order_id
    _next_order_id += 1
    return current


reset()
