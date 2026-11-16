"""Relay entre o Alertmanager e o GitHub.

Recebe o webhook do Alertmanager, junta métricas do Prometheus e logs de erro do
Loki e dispara o evento `anomaly-detected` no repositório, que inicia o workflow
de análise de incidente.
"""

import logging
import os
import time

import httpx
from fastapi import FastAPI

GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")

METRIC_QUERIES = {
    "requests_per_second": "sum(rate(orderservice_http_requests_total[5m]))",
    "error_rate_5xx": (
        'sum(rate(orderservice_http_requests_total{status=~"5.."}[5m]))'
        " / sum(rate(orderservice_http_requests_total[5m]))"
    ),
    "latency_p95_seconds": (
        "histogram_quantile(0.95, sum by (le) (rate(orderservice_http_request_duration_seconds_bucket[5m])))"
    ),
    "errors_by_route": 'sum by (route, status) (rate(orderservice_http_requests_total{status=~"5.."}[5m]))',
}
LOG_QUERY = '{service="orderservice"} | json | level="ERROR" or status >= 500'
MAX_LOG_LINES = 50
MAX_LOG_LINE_CHARS = 1500

logger = logging.getLogger("relay")
app = FastAPI(title="GenAI alert relay")


def query_metrics(client: httpx.Client) -> dict:
    snapshot = {}
    for name, query in METRIC_QUERIES.items():
        try:
            resp = client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query})
            resp.raise_for_status()
            snapshot[name] = [
                {"labels": r["metric"], "value": r["value"][1]} for r in resp.json()["data"]["result"]
            ]
        except httpx.HTTPError as exc:
            snapshot[name] = f"erro ao consultar: {exc}"
    return snapshot


def query_error_logs(client: httpx.Client) -> list[str]:
    now_ns = time.time_ns()
    try:
        resp = client.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": LOG_QUERY,
                "start": now_ns - 15 * 60 * 10**9,
                "end": now_ns,
                "limit": MAX_LOG_LINES,
                "direction": "backward",
            },
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        return [f"erro ao consultar o Loki: {exc}"]
    lines = [line for stream in resp.json()["data"]["result"] for _, line in stream["values"]]
    return [line[:MAX_LOG_LINE_CHARS] for line in lines[:MAX_LOG_LINES]]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/alertmanager")
def alertmanager_webhook(notification: dict) -> dict:
    firing = [a for a in notification.get("alerts", []) if a.get("status") == "firing"]
    if not firing:
        return {"dispatched": 0}

    with httpx.Client(timeout=10) as client:
        metrics = query_metrics(client)
        logs = query_error_logs(client)

        # O GitHub aceita no máximo 10 propriedades no primeiro nível do client_payload.
        first = firing[0]
        payload = {
            "alertname": first["labels"].get("alertname"),
            "severity": first["labels"].get("severity"),
            "summary": first.get("annotations", {}).get("summary"),
            "description": first.get("annotations", {}).get("description"),
            "starts_at": first.get("startsAt"),
            "alerts": [{"labels": a["labels"], "annotations": a.get("annotations", {})} for a in firing],
            "metrics": metrics,
            "error_logs": logs,
        }
        resp = client.post(
            f"https://api.github.com/repos/{GITHUB_REPOSITORY}/dispatches",
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"event_type": "anomaly-detected", "client_payload": payload},
        )
        resp.raise_for_status()

    logger.warning("Evento anomaly-detected enviado para %s (%s)", GITHUB_REPOSITORY, payload["alertname"])
    return {"dispatched": 1}
