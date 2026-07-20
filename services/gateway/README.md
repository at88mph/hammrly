# Hammrly Gateway

Public HTTP edge between clients and the **job submission queues**. It authenticates callers (**JWT**), validates payloads, and publishes to **Redis Streams** (`payload` field):

- **Interactive** → `hammrly:job-submissions` (`JobSubmissionEnvelope`) via **`POST /v2/session`**
- **Headless** → `hammrly:campaign-submissions` (`CampaignExpansionEnvelope`) via **`POST /v2/campaigns`**

Gateway does **not** use PostgreSQL.

See **[SPEC.md](SPEC.md)** for architecture, trust boundaries, error codes, and operations.

## Quick start

```bash
cd services/gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Minimal local dev (symmetric JWT; use JWKS in production)
export HAMMRLY_JWT_DEV_HMAC_SECRET='your-dev-secret-at-least-32-chars-long!!'
export HAMMRLY_REDIS_URL='redis://127.0.0.1:6379/0'

hammrly-gateway
# or: python -m hammrly_gateway.main
```

- **OpenAPI**: `/.well-known/openapi.json` (also `/internal/openapi.json`, `/docs`).
- **Interactive submit**: `POST /v2/session`
- **Headless submit**: `POST /v2/campaigns` (see [`contracts/job-campaign/v1/`](../../contracts/job-campaign/v1/))

Environment variables use prefix **`HAMMRLY_`** (see `hammrly_gateway.config.Settings` and SPEC.md).

## Tests

```bash
export HAMMRLY_REDIS_FAKE=true   # optional; tests default this via conftest
python3 -m pytest tests/ -v
```

### Integration tests (notebook session)

Live tests under `tests/integration/` submit a **notebook** workload via Gateway, poll Query until **`status == "ready"`**, then **`GET`** the job’s **`access_url`** and assert a **2xx** response. They are **skipped** unless explicitly enabled.

**Requirements:** a deployed stack with **orchestrator K8s submit**, **job watch**, and **pod watch** enabled; ingress host and path aligned between gateway and orchestrator; Redis and Postgres shared by orchestrator and query; the same **`HAMMRLY_JWT_DEV_HMAC_SECRET`** on gateway and query.

```bash
cd services/gateway
pip install -e ".[dev]"

export HAMMRLY_INTEGRATION=1
export HAMMRLY_GATEWAY_URL='https://your-gateway.example'   # default http://localhost:8080
export HAMMRLY_QUERY_URL='https://your-query.example'       # default http://localhost:8081
export HAMMRLY_JWT_DEV_HMAC_SECRET='your-dev-secret-at-least-32-chars-long!!'
# Optional: HAMMRLY_INTEGRATION_INSECURE_TLS=1  (self-signed ingress)
# Optional: HAMMRLY_INTEGRATION_TIMEOUT_SEC=900
# Optional: HAMMRLY_NOTEBOOK_IMAGE=jupyter/minimal-notebook:latest

python3 -m pytest tests/integration/ -v -m integration
```

`docker compose` alone does **not** run notebook workloads in Kubernetes; use a cluster install of [`helm/stack`](../../helm/stack) with `orchestrator.k8sSubmitEnabled: true` and ingress configured.
