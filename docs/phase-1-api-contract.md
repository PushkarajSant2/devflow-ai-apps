# Phase 1 API Contract

## Payment API

### `GET /healthz`

Returns basic service health.

### `GET /readyz`

Returns readiness. The service returns `503` when failure mode is `not_ready`.

### `GET /metrics`

Returns Prometheus-style plaintext metrics.

### `POST /api/payments/checkout`

Request:

```json
{
  "order_id": "ord_123",
  "amount": 1200.5,
  "currency": "INR"
}
```

Response:

```json
{
  "payment_id": "pay_...",
  "order_id": "ord_123",
  "status": "approved",
  "amount": 1200.5,
  "currency": "INR"
}
```

### `POST /admin/failure-mode`

Request:

```json
{
  "mode": "db_timeout",
  "random_error_rate": 0.5
}
```

Allowed modes:

- `healthy`
- `db_timeout`
- `random_errors`
- `not_ready`

## Order API

### `POST /api/orders`

Request:

```json
{
  "customer_id": "cust_001",
  "items": [
    {
      "sku": "book-001",
      "quantity": 1,
      "price": 499
    }
  ]
}
```

Response:

```json
{
  "order_id": "ord_...",
  "status": "confirmed",
  "total": 499,
  "payment": {
    "status": "approved"
  }
}
```
