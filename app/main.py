from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import repository, services
from app.models import Order, OrderIn, Product
from app.observability import ORDERS_CREATED, configure_logging, instrument

logger = configure_logging()

app = FastAPI(title="OrderService", version="0.1.0", description="API de processamento de pedidos")
instrument(app, logger)


@app.exception_handler(services.OrderError)
async def order_error_handler(request: Request, exc: services.OrderError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/products", response_model=list[Product])
def list_products() -> list[Product]:
    return list(repository.products.values())


@app.post("/orders", response_model=Order, status_code=201)
def create_order(data: OrderIn) -> Order:
    order = services.create_order(data)
    ORDERS_CREATED.inc()
    return order


@app.get("/orders", response_model=list[Order])
def list_orders() -> list[Order]:
    return list(repository.orders.values())


@app.get("/orders/{order_id}", response_model=Order)
def get_order(order_id: int) -> Order:
    return services.get_order(order_id)


@app.post("/orders/{order_id}/pay", response_model=Order)
def pay_order(order_id: int) -> Order:
    return services.pay_order(order_id)


@app.post("/orders/{order_id}/ship", response_model=Order)
def ship_order(order_id: int) -> Order:
    return services.ship_order(order_id)


@app.post("/orders/{order_id}/cancel", response_model=Order)
def cancel_order(order_id: int) -> Order:
    return services.cancel_order(order_id)
