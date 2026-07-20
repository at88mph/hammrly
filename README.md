# Hammrly

Platform services for **authenticated job submission** over HTTP, durable **Redis Streams** handoff to a **queue worker (orchestrator)**, optional **Kubernetes** execution (**Kueue** / suspended Jobs), and **PostgreSQL** lifecycle storage with a **read-only query API**.

---

## What’s in this repo

| Path | Purpose |
|------|--------|
| [`contracts/job-submission/v1/`](contracts/job-submission/v1/) | Canonical **`JobSubmissionEnvelope`** JSON Schema and validation notes |
| [`services/gateway/`](services/gateway/) | HTTP edge: JWT, validation, `XADD` to Redis — **`POST /v2/session`** (interactive), **`POST /v2/campaigns`** (headless) |
| [`services/orchestrator/`](services/orchestrator/) | Redis consumer, persistence writer, optional Kubernetes submitter / Job watch |
| [`services/query/`](services/query/) | Read-only HTTP API over the same DB tables (`GET /v1/jobs/...`, interactive list) |
| [`helm/gateway`](helm/gateway), [`helm/orchestrator`](helm/orchestrator), [`helm/query`](helm/query) | Helm charts per service |
| [`helm/stack`](helm/stack) | Umbrella chart that installs all three (bring your own Redis + Postgres) |
| [`compose.yaml`](compose.yaml) | Local stack: Redis, Postgres, migrations, gateway, orchestrator, query (no Kubernetes) |

Service details, env vars, and ops: **gateway** [`SPEC.md`](services/gateway/SPEC.md), **orchestrator** [`SPEC.md`](services/orchestrator/SPEC.md), **query** [`SPEC.md`](services/query/SPEC.md).

---

## Job submission — architecture

Incoming requests carry a **JSON workload** that is wrapped in a **`JobSubmissionEnvelope`** (see schema). The gateway **never** writes PostgreSQL; the orchestrator is the **sole automated writer** of submission lifecycle rows.

![Job submission architecture](docs/diagrams/architecture.svg)

*Diagram source: [`docs/diagrams/architecture.mmd`](docs/diagrams/architecture.mmd). Rendered as SVG because GitLab's sandboxed Mermaid iframe currently fails to load its webpack bundles (CSP `script-src` error).*

### Submit path (sequence)

![Submit path sequence](docs/diagrams/submit-path.svg)

*Diagram source: [`docs/diagrams/submit-path.mmd`](docs/diagrams/submit-path.mmd).*

### Workload Job anatomy (Pod)

When Kubernetes submission is enabled, each workload runs as a **Job** whose **Pod** has three cooperating containers sharing an `emptyDir` workspace at `/workspace`:

1. **Input staging container** (`input-downloader` init container) — downloads optional `workload.input_uri` into `/workspace/inputs`, then exits.
2. **Processing container** (`workload` container) — runs the submitted image, reads inputs, writes products under `/workspace/outputs`, and signals completion by writing `hammrly-complete.json` (or `hammrly-error.json` on failure). See the [workload completion contract](contracts/workload-completion/v1/README.md).
3. **Output container** (`output-watcher` sidecar) — watches for the completion manifest and uploads listed outputs to external storage (using per-output `destination_uri` values or the job’s `workload.output_uri` prefix).

![Workload Job anatomy](docs/diagrams/job-anatomy.svg)

*Diagram source: [`docs/diagrams/job-anatomy.mmd`](docs/diagrams/job-anatomy.mmd).*

### Contract and stream wire format

- **Envelope**: [`contracts/job-submission/v1/schema.json`](contracts/job-submission/v1/schema.json)
- **Redis**: stream key **`hammrly:job-submissions`**, field **`payload`** (UTF-8 JSON). See [`contracts/job-submission/v1/README.md`](contracts/job-submission/v1/README.md).

---

## Prerequisites

- **Docker** + [Compose V2](https://docs.docker.com/compose/) for the local stack, **or**
- **Kubernetes 1.30+** + **Helm 3.14+** for production-style deploy  
- **PostgreSQL** and **Redis** available to the stack (Compose provides both; Helm charts expect you to point URLs at existing instances)

---

## Deploy with Docker Compose

The repo root [`compose.yaml`](compose.yaml) starts **PostgreSQL**, **Redis**, runs **Alembic migrations** once (`migrate` service), then **gateway** (port **8080**), **orchestrator** (stream consumer + DB, **Kubernetes disabled**), and **query** (port **8081**).

From the **repository root**:

```bash
docker compose up --build
```

Optional: set a dev JWT secret (must be **≥ 32** characters for gateway/query):

```bash
export HAMMRLY_JWT_DEV_HMAC_SECRET='your-dev-secret-at-least-32-chars-long'
docker compose up --build
```

| URL | Notes |
|-----|--------|
| http://localhost:8080 | Gateway — OpenAPI at `/.well-known/openapi.json`, submit at `POST /v2/session` |
| http://localhost:8081 | Query — OpenAPI at `/.well-known/openapi.json` |

Compose sets **`HAMMRLY_CLUSTER_ID=docker-compose`** on orchestrator and query so listings stay consistent. For a real cluster, align **`cluster_id`** (or leave orchestrator default and omit query’s filter).

**Production note:** Compose is for **local/demo** only. Use JWKS-backed JWT and secrets management in real environments.

### Submit a notebook job (example)

With the stack running, mint a dev JWT (HS256; matches the default `HAMMRLY_JWT_DEV_HMAC_SECRET` in [`compose.yaml`](compose.yaml)). Requires [PyJWT](https://pyjwt.readthedocs.io/) (`pip install pyjwt`):

```bash
export HAMMRLY_JWT_DEV_HMAC_SECRET='dev-hammrly-jwt-secret-min-32b!!'
export TOKEN=$(python3 -c "
import os, jwt
secret = os.environ['HAMMRLY_JWT_DEV_HMAC_SECRET']
print(jwt.encode(
    {'sub': 'user-1', 'hammrly_tenant_id': 'demo-tenant', 'scope': 'hammrly:jobs:submit'},
    secret,
    algorithm='HS256',
))
")
```

Submit an interactive Jupyter workload:

```bash
curl -sS -X POST http://localhost:8080/v2/session \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "my-project",
    "workload": {
      "kind": "notebook",
      "name": "analysis-notebook",
      "image": "jupyter/minimal-notebook:latest",
      "resources": {
        "cpu": "2",
        "memory": "4Gi"
      },
      "kind_options": {
        "jupyter": {"port": 8888}
      }
    }
  }'
```

On success the gateway returns **`202 Accepted`** with `job_id`, `submission_id`, **`status: "PENDING"`**, and **`status_url`** (Query API path to poll job state, e.g. `/v1/jobs/{job_id}`). Poll that Query endpoint; early responses may show **`status: "pending"`** from the Redis job index before the orchestrator persists the row.

Poll the query API until the session is ready to open:

```bash
# Replace JOB_ID from the gateway response
curl -sS "http://localhost:8081/v1/jobs/JOB_ID" \
  -H "Authorization: Bearer ${TOKEN}"
```

Treat **`status == "ready"`** as the signal to open **`access_url`** in a browser. Until then, status progresses through `received` → `submitted_to_cluster` → `admitted` → `running` → `ready`, and `events[]` includes `access_url_set` (provisional) then `session_ready` (openable).

Submit an interactive desktop workload (image is caller-chosen; use your published `desktop-base` / `desktop-astronomy` image when available):

```bash
curl -sS -X POST http://localhost:8080/v2/session \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "my-project",
    "workload": {
      "kind": "desktop",
      "name": "my-desktop",
      "image": "registry.example/hammrly/desktop-astronomy:1.0",
      "resources": {
        "cpu": "4",
        "memory": "8Gi"
      },
      "kind_options": {
        "novnc": {"port": 6080}
      }
    }
  }'
```

Poll query the same way as notebook until **`status == "ready"`**, then open **`access_url`**.

The same contract applies to all interactive kinds (`desktop`, `notebook`, `carta`, `contributed`). For **`contributed`** workloads you must include **`kind_options.probes.readiness`** in the submit payload. In production, use your platform-issued JWT instead of the dev HMAC secret.

---

## Deploy with Helm

Charts live under [`helm/`](helm/). Build images from the **repo root** (tag / registry as you prefer):

```bash
docker build -f services/gateway/Dockerfile -t hammrly/gateway:0.1.0 .
docker build -f services/orchestrator/Dockerfile -t hammrly/orchestrator:0.1.0 .
docker build -f services/query/Dockerfile -t hammrly/query:0.1.0 .
```

Vendor subcharts and install the **umbrella** chart [`helm/stack`](helm/stack) (does **not** install Redis or Postgres):

```bash
cd helm/stack
helm dependency update
helm install hammrly . -n hammrly --create-namespace \
  -f values.yaml \
  --set gateway.redisUrl=redis://your-redis:6379/0 \
  --set orchestrator.redisUrl=redis://your-redis:6379/0 \
  --set orchestrator.database.url='postgresql+psycopg2://user:pass@postgres:5432/hammrly' \
  --set query.database.url='postgresql+psycopg2://user:pass@postgres:5432/hammrly' \
  --set gateway.jwt.devHmacSecret='replace-with-secret' \
  --set query.jwt.devHmacSecret='replace-with-secret'
```

Production orchestrator and query DB: **`database.url`** as `host:port/dbname` plus a Secret for **username** and **password** only (see [`helm/stack/README.md`](helm/stack/README.md)). For a quick demo, **`database.url`** may be a full DSN containing **`://`**. Both services **require** PostgreSQL (`HAMMRLY_DATABASE_URL`).

- **Orchestrator RBAC** and **`k8sWorkloadNamespace`**: see [`helm/stack/README.md`](helm/stack/README.md).
- **Production:** use **`jwt.jwksUrl`** (and issuer / audience) instead of dev HMAC secrets.

Single-service installs: `helm/gateway`, `helm/orchestrator`, `helm/query`.

---

## Development (without Compose)

Each service has a `README.md` under `services/<name>/` with venv install and pytest. Database migrations (orchestrator):

```bash
cd services/orchestrator
export HAMMRLY_DATABASE_URL='postgresql+psycopg2://user:pass@localhost:5432/hammrly'
PYTHONPATH=src alembic upgrade head
```

---

## Related documentation

- [Job submission contract README](contracts/job-submission/v1/README.md)
- [Validation matrix](contracts/job-submission/v1/VALIDATION.md)
