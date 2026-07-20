# Hammrly Query

Read-only HTTP API over the same **`submissions`** / **`submission_events`** PostgreSQL tables as the orchestrator. Use a **replica DSN** or database role granted **SELECT** only.

See **[SPEC.md](SPEC.md)** for auth, endpoints, and deployment.

## Quick start

```bash
cd services/query
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export HAMMRLY_DATABASE_URL='postgresql+psycopg2://readonly:pass@localhost:5432/hammrly'
export HAMMRLY_JWT_DEV_HMAC_SECRET='your-dev-secret-at-least-32-chars-long!!'   # dev only

hammrly-query
# or: python -m hammrly_query.main
```

- **OpenAPI**: `/.well-known/openapi.json`
- **Job by id**: `GET /v1/jobs/{job_id}`
- **My interactive jobs**: `GET /v1/me/jobs/interactive`

Default listen port is **8081** (gateway defaults to 8080).

## Tests

```bash
HAMMRLY_SKIP_DB_BOOTSTRAP=true python3 -m pytest tests/ -v
```

(`tests/conftest.py` sets this by default; mocks DB via FastAPI dependency overrides.)
