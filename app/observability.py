"""Logs estruturados em JSON e métricas Prometheus."""

import json
import logging
import sys
import time

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter(
    "orderservice_http_requests_total",
    "Total de requisições HTTP",
    ["method", "route", "status"],
)
LATENCY = Histogram(
    "orderservice_http_request_duration_seconds",
    "Latência das requisições HTTP",
    ["method", "route"],
)
ORDERS_CREATED = Counter("orderservice_orders_created_total", "Pedidos criados")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "extra_fields", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("orderservice")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def instrument(app: FastAPI, logger: logging.Logger) -> None:
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception:
            logger.exception("Erro não tratado", extra={"extra_fields": {"path": request.url.path}})
            raise
        finally:
            route = request.scope.get("route")
            route_path = route.path if route else request.url.path
            elapsed = time.perf_counter() - start
            REQUESTS.labels(request.method, route_path, str(status)).inc()
            LATENCY.labels(request.method, route_path).observe(elapsed)
            logger.info(
                "request",
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "route": route_path,
                        "status": status,
                        "duration_ms": round(elapsed * 1000, 2),
                    }
                },
            )

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
