"""Gera tráfego no OrderService, incluindo requisições que exploram os trechos frágeis.

Cupons como "PROMOXX" fazem services.coupon_discount_rate levantar ValueError
(HTTP 500), o que dispara o alerta OrderServiceHighErrorRate em poucos minutos.

Uso: python scripts/generate_traffic.py [URL_BASE] [SEGUNDOS]
"""

import json
import random
import sys
import time
import urllib.error
import urllib.request

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
DURATION = int(sys.argv[2]) if len(sys.argv) > 2 else 300


def post_order(coupon: str | None) -> int:
    body = {"customer_email": "carga@example.com", "items": [{"product_id": random.choice([1, 2]), "quantity": 1}]}
    if coupon:
        body["coupon"] = coupon
    req = urllib.request.Request(
        f"{BASE_URL}/orders",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main() -> None:
    deadline = time.time() + DURATION
    stats: dict[int, int] = {}
    while time.time() < deadline:
        coupon = random.choice([None, "PROMO10", "PROMOXX", "BLACKFRIDAY"])
        status = post_order(coupon)
        stats[status] = stats.get(status, 0) + 1
        time.sleep(0.2)
    print("Respostas por status:", stats)


if __name__ == "__main__":
    main()
