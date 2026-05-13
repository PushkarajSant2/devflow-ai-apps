from __future__ import annotations

import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any
from urllib.parse import urlparse


SERVICE_NAME = "payment-api"
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
PORT = int(os.getenv("PORT", "8080"))
ALLOWED_FAILURE_MODES = {"healthy", "db_timeout", "random_errors", "not_ready"}


class AppState:
    def __init__(self) -> None:
        self.lock = Lock()
        self.failure_mode = os.getenv("FAILURE_MODE", "healthy")
        if self.failure_mode not in ALLOWED_FAILURE_MODES:
            self.failure_mode = "healthy"
        self.random_error_rate = float(os.getenv("RANDOM_ERROR_RATE", "0.5"))
        self.started_at = time.time()
        self.http_requests: dict[tuple[str, str, int], int] = {}
        self.checkouts: dict[str, int] = {
            "approved": 0,
            "rejected": 0,
            "failed": 0,
        }

    def record_http(self, method: str, route: str, status: int) -> None:
        with self.lock:
            key = (method, route, status)
            self.http_requests[key] = self.http_requests.get(key, 0) + 1

    def record_checkout(self, outcome: str) -> None:
        with self.lock:
            self.checkouts[outcome] = self.checkouts.get(outcome, 0) + 1

    def set_failure_mode(self, mode: str, random_error_rate: float | None = None) -> None:
        if mode not in ALLOWED_FAILURE_MODES:
            raise ValueError(f"unsupported failure mode: {mode}")
        with self.lock:
            self.failure_mode = mode
            if random_error_rate is not None:
                self.random_error_rate = max(0.0, min(1.0, random_error_rate))

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "service": SERVICE_NAME,
                "version": SERVICE_VERSION,
                "failure_mode": self.failure_mode,
                "random_error_rate": self.random_error_rate,
                "uptime_seconds": round(time.time() - self.started_at, 2),
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


def make_payment_id() -> str:
    return f"pay_{uuid.uuid4().hex[:16]}"


def prometheus_metrics() -> str:
    snapshot = STATE.snapshot()
    lines = [
        "# HELP devflow_service_info Static service information.",
        "# TYPE devflow_service_info gauge",
        f'devflow_service_info{{service="{SERVICE_NAME}",version="{SERVICE_VERSION}"}} 1',
        "# HELP devflow_payment_failure_mode Current failure mode by label.",
        "# TYPE devflow_payment_failure_mode gauge",
    ]

    for mode in sorted(ALLOWED_FAILURE_MODES):
        value = 1 if snapshot["failure_mode"] == mode else 0
        lines.append(f'devflow_payment_failure_mode{{mode="{mode}"}} {value}')

    lines.extend(
        [
            "# HELP http_requests_total Total HTTP requests.",
            "# TYPE http_requests_total counter",
        ]
    )
    with STATE.lock:
        for (method, route, status), count in sorted(STATE.http_requests.items()):
            lines.append(
                f'http_requests_total{{service="{SERVICE_NAME}",method="{method}",route="{route}",status="{status}"}} {count}'
            )

        lines.extend(
            [
                "# HELP devflow_payment_checkouts_total Total checkout outcomes.",
                "# TYPE devflow_payment_checkouts_total counter",
            ]
        )
        for outcome, count in sorted(STATE.checkouts.items()):
            lines.append(f'devflow_payment_checkouts_total{{outcome="{outcome}"}} {count}')

    lines.append("")
    return "\n".join(lines)


class PaymentHandler(BaseHTTPRequestHandler):
    server_version = "DevFlowPayment/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _route(self) -> str:
        return urlparse(self.path).path

    def _request_id(self) -> str:
        return self.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"

    def _send_json(self, status: int, body: dict[str, Any], request_id: str) -> None:
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
                snapshot = STATE.snapshot()
                ready = snapshot["failure_mode"] != "not_ready"
                status = HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE
                self._send_json(
                    status,
                    {
                        "status": "ready" if ready else "not_ready",
                        **snapshot,
                    },
                    request_id,
                )
            elif route == "/metrics":
                status = HTTPStatus.OK
                self._send_text(status, prometheus_metrics(), "text/plain; version=0.0.4", request_id)
            elif route == "/admin/failure-mode":
                status = HTTPStatus.OK
                self._send_json(status, STATE.snapshot(), request_id)
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
            if route == "/api/payments/checkout":
                status = self._handle_checkout(request_id)
            elif route == "/admin/failure-mode":
                body = read_json(self)
                mode = str(body.get("mode", "healthy"))
                random_error_rate = body.get("random_error_rate")
                STATE.set_failure_mode(
                    mode,
                    float(random_error_rate) if random_error_rate is not None else None,
                )
                status = HTTPStatus.OK
                self._send_json(status, {"message": "failure mode updated", **STATE.snapshot()}, request_id)
            elif route == "/admin/break":
                STATE.set_failure_mode("db_timeout")
                status = HTTPStatus.OK
                self._send_json(status, {"message": "payment service is now simulating db_timeout", **STATE.snapshot()}, request_id)
            elif route == "/admin/recover":
                STATE.set_failure_mode("healthy")
                status = HTTPStatus.OK
                self._send_json(status, {"message": "payment service recovered", **STATE.snapshot()}, request_id)
            else:
                self._send_json(status, {"error": "not_found", "route": route}, request_id)
        except ValueError as exc:
            status = HTTPStatus.BAD_REQUEST
            self._send_json(status, {"error": "bad_request", "message": str(exc)}, request_id)
        except json.JSONDecodeError:
            status = HTTPStatus.BAD_REQUEST
            self._send_json(status, {"error": "invalid_json"}, request_id)
        except Exception as exc:  # noqa: BLE001
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            log_event("error", "unhandled request error", request_id=request_id, route=route, error=str(exc))
            self._send_json(status, {"error": "internal_error", "request_id": request_id}, request_id)
        finally:
            self._finish("POST", route, int(status), request_id, started_at)

    def _handle_checkout(self, request_id: str) -> HTTPStatus:
        body = read_json(self)
        order_id = str(body.get("order_id", "")).strip()
        amount = float(body.get("amount", 0))
        currency = str(body.get("currency", "INR")).upper()

        if not order_id:
            STATE.record_checkout("rejected")
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "order_id_required"}, request_id)
            return HTTPStatus.BAD_REQUEST

        if amount <= 0:
            STATE.record_checkout("rejected")
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "amount_must_be_positive"}, request_id)
            return HTTPStatus.BAD_REQUEST

        snapshot = STATE.snapshot()
        failure_mode = snapshot["failure_mode"]

        if failure_mode == "db_timeout":
            time.sleep(1.2)
            STATE.record_checkout("failed")
            log_event(
                "error",
                "checkout failed because database timed out",
                request_id=request_id,
                order_id=order_id,
                failure_mode=failure_mode,
            )
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "database_timeout",
                    "message": "simulated database timeout while authorizing payment",
                    "order_id": order_id,
                },
                request_id,
            )
            return HTTPStatus.SERVICE_UNAVAILABLE

        if failure_mode == "random_errors" and random.random() < snapshot["random_error_rate"]:
            STATE.record_checkout("failed")
            log_event(
                "error",
                "checkout failed due to random error mode",
                request_id=request_id,
                order_id=order_id,
                failure_mode=failure_mode,
            )
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "random_payment_gateway_error",
                    "message": "simulated intermittent payment provider failure",
                    "order_id": order_id,
                },
                request_id,
            )
            return HTTPStatus.INTERNAL_SERVER_ERROR

        payment = {
            "payment_id": make_payment_id(),
            "order_id": order_id,
            "status": "approved",
            "amount": amount,
            "currency": currency,
            "service_version": SERVICE_VERSION,
        }
        STATE.record_checkout("approved")
        self._send_json(HTTPStatus.OK, payment, request_id)
        return HTTPStatus.OK


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), PaymentHandler)
    log_event("info", "service starting", port=PORT, version=SERVICE_VERSION)
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
