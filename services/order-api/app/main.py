from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


SERVICE_NAME = "order-api"
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
PORT = int(os.getenv("PORT", "8081"))
PAYMENT_API_URL = os.getenv("PAYMENT_API_URL", "http://localhost:8080").rstrip("/")
PAYMENT_TIMEOUT_SECONDS = float(os.getenv("PAYMENT_TIMEOUT_SECONDS", "2.0"))


class AppState:
    def __init__(self) -> None:
        self.lock = Lock()
        self.started_at = time.time()
        self.orders: list[dict[str, Any]] = []
        self.http_requests: dict[tuple[str, str, int], int] = {}
        self.order_outcomes: dict[str, int] = {
            "confirmed": 0,
            "payment_failed": 0,
            "rejected": 0,
        }

    def record_http(self, method: str, route: str, status: int) -> None:
        with self.lock:
            key = (method, route, status)
            self.http_requests[key] = self.http_requests.get(key, 0) + 1

    def record_order(self, outcome: str) -> None:
        with self.lock:
            self.order_outcomes[outcome] = self.order_outcomes.get(outcome, 0) + 1

    def add_order(self, order: dict[str, Any]) -> None:
        with self.lock:
            self.orders.append(order)

    def list_orders(self) -> list[dict[str, Any]]:
        with self.lock:
            return list(reversed(self.orders[-20:]))

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "service": SERVICE_NAME,
                "version": SERVICE_VERSION,
                "payment_api_url": PAYMENT_API_URL,
                "uptime_seconds": round(time.time() - self.started_at, 2),
                "orders_stored": len(self.orders),
            }


STATE = AppState()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(level: str, message: str, **fields: Any) -> None:
    event = {
        "timestamp": utc_now(),
        "level": level,
        "service": SERVICE_NAME,
        "message": message,
        **fields,
    }
    print(json.dumps(event, separators=(",", ":")), flush=True)


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    raw_length = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw_length)
    except ValueError:
        length = 0
    if length <= 0:
        return {}
    raw_body = handler.rfile.read(length)
    if not raw_body:
        return {}
    return json.loads(raw_body.decode("utf-8"))


def make_order_id() -> str:
    return f"ord_{uuid.uuid4().hex[:16]}"


def calculate_total(items: list[dict[str, Any]]) -> float:
    total = 0.0
    for item in items:
        quantity = int(item.get("quantity", 0))
        price = float(item.get("price", 0))
        if quantity <= 0 or price <= 0:
            raise ValueError("each item must have positive quantity and price")
        total += quantity * price
    return round(total, 2)


def call_payment_api(order_id: str, amount: float, request_id: str) -> tuple[int, dict[str, Any]]:
    payload = json.dumps(
        {
            "order_id": order_id,
            "amount": amount,
            "currency": "INR",
        }
    ).encode("utf-8")
    request = Request(
        f"{PAYMENT_API_URL}/api/payments/checkout",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        },
    )

    try:
        with urlopen(request, timeout=PAYMENT_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
            return int(response.status), body
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8") if exc.fp else "{}"
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            body = {"error": "payment_api_error", "message": raw_body}
        return int(exc.code), body
    except URLError as exc:
        return HTTPStatus.BAD_GATEWAY, {
            "error": "payment_api_unreachable",
            "message": str(exc.reason),
        }
    except TimeoutError:
        return HTTPStatus.GATEWAY_TIMEOUT, {
            "error": "payment_api_timeout",
            "message": "payment API call timed out",
        }


def check_payment_readiness() -> bool:
    request = Request(f"{PAYMENT_API_URL}/readyz", method="GET")
    try:
        with urlopen(request, timeout=1.0) as response:
            return int(response.status) == HTTPStatus.OK
    except Exception:  # noqa: BLE001
        return False


def prometheus_metrics() -> str:
    lines = [
        "# HELP devflow_service_info Static service information.",
        "# TYPE devflow_service_info gauge",
        f'devflow_service_info{{service="{SERVICE_NAME}",version="{SERVICE_VERSION}"}} 1',
        "# HELP http_requests_total Total HTTP requests.",
        "# TYPE http_requests_total counter",
    ]

    with STATE.lock:
        for (method, route, status), count in sorted(STATE.http_requests.items()):
            lines.append(
                f'http_requests_total{{service="{SERVICE_NAME}",method="{method}",route="{route}",status="{status}"}} {count}'
            )

        lines.extend(
            [
                "# HELP devflow_orders_total Total order outcomes.",
                "# TYPE devflow_orders_total counter",
            ]
        )
        for outcome, count in sorted(STATE.order_outcomes.items()):
            lines.append(f'devflow_orders_total{{outcome="{outcome}"}} {count}')

        lines.extend(
            [
                "# HELP devflow_orders_stored Current in-memory order count.",
                "# TYPE devflow_orders_stored gauge",
                f"devflow_orders_stored {len(STATE.orders)}",
            ]
        )

    lines.append("")
    return "\n".join(lines)


class OrderHandler(BaseHTTPRequestHandler):
    server_version = "DevFlowOrder/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _route(self) -> str:
        return urlparse(self.path).path

    def _request_id(self) -> str:
        return self.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"

    def _send_json(self, status: int, body: dict[str, Any] | list[dict[str, Any]], request_id: str) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Request-ID", request_id)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Request-ID")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, status: int, body: str, content_type: str, request_id: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Request-ID", request_id)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _finish(self, method: str, route: str, status: int, request_id: str, started_at: float) -> None:
        latency_ms = round((time.time() - started_at) * 1000, 2)
        STATE.record_http(method, route, status)
        log_event(
            "info",
            "request completed",
            request_id=request_id,
            method=method,
            route=route,
            status=status,
            latency_ms=latency_ms,
        )

    def do_OPTIONS(self) -> None:
        request_id = self._request_id()
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Request-ID")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("X-Request-ID", request_id)
        self.end_headers()

    def do_GET(self) -> None:
        started_at = time.time()
        request_id = self._request_id()
        route = self._route()
        status = HTTPStatus.NOT_FOUND

        try:
            if route == "/healthz":
                status = HTTPStatus.OK
                self._send_json(status, {"status": "ok", **STATE.snapshot()}, request_id)
            elif route == "/readyz":
                payment_ready = check_payment_readiness()
                status = HTTPStatus.OK if payment_ready else HTTPStatus.SERVICE_UNAVAILABLE
                self._send_json(
                    status,
                    {
                        "status": "ready" if payment_ready else "dependency_not_ready",
                        "payment_api_ready": payment_ready,
                        **STATE.snapshot(),
                    },
                    request_id,
                )
            elif route == "/metrics":
                status = HTTPStatus.OK
                self._send_text(status, prometheus_metrics(), "text/plain; version=0.0.4", request_id)
            elif route == "/api/orders":
                status = HTTPStatus.OK
                self._send_json(status, STATE.list_orders(), request_id)
            else:
                self._send_json(status, {"error": "not_found", "route": route}, request_id)
        except Exception as exc:  # noqa: BLE001
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            log_event("error", "unhandled request error", request_id=request_id, route=route, error=str(exc))
            self._send_json(status, {"error": "internal_error", "request_id": request_id}, request_id)
        finally:
            self._finish("GET", route, int(status), request_id, started_at)

    def do_POST(self) -> None:
        started_at = time.time()
        request_id = self._request_id()
        route = self._route()
        status = HTTPStatus.NOT_FOUND

        try:
            if route == "/api/orders":
                status = self._handle_create_order(request_id)
            else:
                self._send_json(status, {"error": "not_found", "route": route}, request_id)
        except ValueError as exc:
            status = HTTPStatus.BAD_REQUEST
            STATE.record_order("rejected")
            self._send_json(status, {"error": "bad_request", "message": str(exc)}, request_id)
        except json.JSONDecodeError:
            status = HTTPStatus.BAD_REQUEST
            STATE.record_order("rejected")
            self._send_json(status, {"error": "invalid_json"}, request_id)
        except Exception as exc:  # noqa: BLE001
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            log_event("error", "unhandled request error", request_id=request_id, route=route, error=str(exc))
            self._send_json(status, {"error": "internal_error", "request_id": request_id}, request_id)
        finally:
            self._finish("POST", route, int(status), request_id, started_at)

    def _handle_create_order(self, request_id: str) -> HTTPStatus:
        body = read_json(self)
        customer_id = str(body.get("customer_id", "")).strip()
        items = body.get("items")

        if not customer_id:
            raise ValueError("customer_id is required")
        if not isinstance(items, list) or not items:
            raise ValueError("items must be a non-empty list")

        total = calculate_total(items)
        order_id = make_order_id()

        payment_status, payment_body = call_payment_api(order_id, total, request_id)
        if payment_status != HTTPStatus.OK:
            STATE.record_order("payment_failed")
            log_event(
                "error",
                "order checkout failed because payment dependency failed",
                request_id=request_id,
                order_id=order_id,
                payment_status=payment_status,
                payment_error=payment_body.get("error"),
            )
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {
                    "order_id": order_id,
                    "status": "payment_failed",
                    "total": total,
                    "payment_status": payment_status,
                    "payment": payment_body,
                },
                request_id,
            )
            return HTTPStatus.BAD_GATEWAY

        order = {
            "order_id": order_id,
            "customer_id": customer_id,
            "status": "confirmed",
            "items": items,
            "total": total,
            "payment": payment_body,
            "service_version": SERVICE_VERSION,
        }
        STATE.add_order(order)
        STATE.record_order("confirmed")
        self._send_json(HTTPStatus.CREATED, order, request_id)
        return HTTPStatus.CREATED


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), OrderHandler)
    log_event(
        "info",
        "service starting",
        port=PORT,
        version=SERVICE_VERSION,
        payment_api_url=PAYMENT_API_URL,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log_event("info", "service stopping")
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        log_event("error", "failed to start service", error=str(exc), port=PORT)
        sys.exit(1)
