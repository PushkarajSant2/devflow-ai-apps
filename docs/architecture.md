# Phase 1 Architecture

```text
Browser
  |
  | HTTP
  v
frontend
  |
  | HTTP
  v
order-api
  |
  | HTTP
  v
payment-api
```

## Runtime Behavior

`order-api` owns order creation. For every order, it calls `payment-api` to approve the checkout payment.

`payment-api` can be switched into failure modes to simulate production incidents:

- `healthy`
- `db_timeout`
- `random_errors`
- `not_ready`

The failure modes are useful later when Prometheus, Loki, Alertmanager, Argo CD, and the DevFlow AI bot are added.

## Future Platform Mapping

| Current Phase 1 Feature | Future Platform Use |
| --- | --- |
| `/healthz` | Kubernetes liveness probe |
| `/readyz` | Kubernetes readiness probe |
| `/metrics` | Prometheus scraping |
| JSON logs | Loki ingestion |
| failure mode | incident simulation |
| service dependency | tracing and root-cause correlation |
| frontend demo | recruiter/interview walkthrough |
