# payment-api

Small payment service used by DevFlow AI demos.

## Run

```powershell
python .\app\main.py
```

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8080` | HTTP port |
| `SERVICE_VERSION` | `1.0.0` | Version returned by health responses |
| `FAILURE_MODE` | `healthy` | Initial failure mode |
| `RANDOM_ERROR_RATE` | `0.5` | Error rate when mode is `random_errors` |

## Failure Modes

```powershell
Invoke-RestMethod -Method Post http://localhost:8080/admin/break
Invoke-RestMethod -Method Post http://localhost:8080/admin/recover
```
