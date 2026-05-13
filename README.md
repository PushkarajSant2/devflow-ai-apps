# DevFlow AI Apps

Phase 1 sample application for DevFlow AI, an AI-native Internal Developer Platform.

This repository contains a small microservice workload that is intentionally designed for later DevOps phases:

- health and readiness endpoints
- Prometheus-style metrics
- structured JSON logs
- controllable failure modes
- service-to-service dependency between APIs
- a tiny frontend for demo workflows

## Services

| Component | Port | Purpose |
| --- | ---: | --- |
| `payment-api` | `8080` | Approves or rejects checkout payments and can simulate production incidents. |
| `order-api` | `8081` | Creates orders and calls `payment-api` during checkout. |
| `frontend` | `5173` | Browser demo UI for creating orders and triggering failures. |

## Local Run

From this folder:

```powershell
.\scripts\start-local.ps1
```

Open:

```text
http://localhost:5173
```

Run a smoke test:

```powershell
.\scripts\smoke-test.ps1
```

Stop local services:

```powershell
.\scripts\stop-local.ps1
```

## Demo Flow

1. Create an order from the frontend.
2. Confirm the order succeeds.
3. Trigger payment failure mode.
4. Create another order.
5. Watch `order-api` fail because its dependency is unhealthy.
6. Recover payment service.
7. Create a successful order again.

This gives future phases a realistic incident story:

```text
New release or dependency issue -> payment failures -> order failures -> metrics/logs change -> alert fires -> AI-Ops bot investigates
```

## API Quick Reference

Payment API:

```text
GET  /healthz
GET  /readyz
GET  /metrics
GET  /admin/failure-mode
POST /admin/failure-mode
POST /admin/break
POST /admin/recover
POST /api/payments/checkout
```

Order API:

```text
GET  /healthz
GET  /readyz
GET  /metrics
GET  /api/orders
POST /api/orders
```

## Why This App Exists

The sample app is not meant to be complex business software. Its job is to behave like a real platform workload so the rest of DevFlow AI can demonstrate:

- CI pipeline
- Docker image build
- vulnerability scanning
- GitOps deployment
- Kubernetes health checks
- service discovery
- observability
- incident alerting
- AI-assisted root cause analysis
