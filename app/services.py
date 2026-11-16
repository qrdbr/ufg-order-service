"""Regras de negócio do OrderService.

Este módulo contém trechos FRÁGEIS DE PROPÓSITO, para servir de alvo
para o agente de IA no pipeline. Eles estão marcados com "FRÁGIL".
"""

from app import repository
from app.models import Order, OrderIn, OrderItem, OrderStatus


class OrderError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def coupon_discount_rate(coupon: str | None) -> float:
    """Cupons no formato PROMO<NN>, ex.: PROMO10 = 10% de desconto."""
    if not coupon:
        return 0.0
    # FRÁGIL: assume que os dois últimos caracteres são dígitos e não limita o
    # percentual. "PROMOXX" levanta ValueError (vira HTTP 500) e "PROMO99" é aceito.
    return int(coupon[-2:]) / 100


def create_order(data: OrderIn) -> Order:
    if not data.items:
        raise OrderError("O pedido precisa de pelo menos um item")

    items: list[OrderItem] = []
    subtotal = 0.0
    for item in data.items:
        product = repository.products.get(item.product_id)
        if product is None:
            raise OrderError(f"Produto {item.product_id} não encontrado", 404)
        # FRÁGIL: não valida quantity <= 0. Quantidade negativa "devolve" estoque
        # e reduz o total do pedido.
        if product.stock < item.quantity:
            raise OrderError(f"Estoque insuficiente para o produto {product.id}", 409)
        # FRÁGIL: o estoque é baixado item a item. Se um item posterior falhar,
        # os anteriores não são devolvidos (não há rollback).
        product.stock -= item.quantity
        items.append(OrderItem(product_id=product.id, quantity=item.quantity, unit_price=product.price))
        # FRÁGIL: valores monetários em float acumulam erro de arredondamento.
        subtotal += product.price * item.quantity

    discount = subtotal * coupon_discount_rate(data.coupon)
    total = round(subtotal - discount, 2)

    order = Order(
        id=repository.next_order_id(),
        customer_email=data.customer_email,  # FRÁGIL: e-mail não é validado
        items=items,
        subtotal=round(subtotal, 2),
        discount=round(discount, 2),
        total=total,
        status=OrderStatus.PENDING,
    )
    repository.orders[order.id] = order
    return order


def get_order(order_id: int) -> Order:
    order = repository.orders.get(order_id)
    if order is None:
        raise OrderError(f"Pedido {order_id} não encontrado", 404)
    return order


def pay_order(order_id: int) -> Order:
    order = get_order(order_id)
    if order.status != OrderStatus.PENDING:
        raise OrderError("Somente pedidos pendentes podem ser pagos", 409)
    order.status = OrderStatus.PAID
    return order


def ship_order(order_id: int) -> Order:
    order = get_order(order_id)
    # FRÁGIL: não verifica se o pedido foi pago antes de enviar.
    order.status = OrderStatus.SHIPPED
    return order


def cancel_order(order_id: int) -> Order:
    order = get_order(order_id)
    # FRÁGIL: permite cancelar pedido já enviado e devolve o estoque duas vezes
    # se o cancelamento for chamado repetidamente.
    for item in order.items:
        repository.products[item.product_id].stock += item.quantity
    order.status = OrderStatus.CANCELLED
    return order
