# order-api

Order service used by DevFlow AI demos. It depends on `payment-api` for checkout authorization.

## Run

```powershell
python .\app\main.py
```

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8081` | HTTP port |
| `SERVICE_VERSION` | `1.0.0` | Version returned by health responses |
| `PAYMENT_API_URL` | `http://localhost:8080` | Dependency URL |
| `PAYMENT_TIMEOUT_SECONDS` | `2.0` | Payment API timeout |
