# Query service — specification

The **query** service exposes a **read-only HTTP API** backed by the same **`submissions`** and **`submission_events`** tables that the **orchestrator** writes ([`services/orchestrator/SPEC.md`](../orchestrator/SPEC.md) §6). It never mutates Kubernetes or the database.

Clients authenticate with **JWT** (same validation model as [**gateway**](../gateway/SPEC.md)) and receive only rows scoped to their **user** (and optional **tenant**) identity.

---

## 1. Responsibilities

| Concern | Owner |
|---------|--------|
| **SELECT** job metadata and timeline events | query |
| JWT **authentication** + read **authorization** (`scope`) | query |
| User/tenant **row scoping** | query |
| Writes, queue publish, K8s | orchestrator / gateway |

---

## 2. Data model

ORM maps the orchestrator schema (see [`../orchestrator/src/hammrly_orchestrator/persistence/models.py`](../orchestrator/src/hammrly_orchestrator/persistence/models.py)):

- **`submissions`**: primary key `submission_id`; unique `job_id`; `user_id`, `tenant_id`, `status`, `payload_summary` (JSONB), K8s binding fields, timestamps, etc.
- **`submission_events`**: append-only events per `submission_id`.

### 2.1 Contract alignment (`contracts/job-submission/v1`)

Queue messages follow **`JobSubmissionEnvelope`** in [`../../contracts/job-submission/v1/schema.json`](../../contracts/job-submission/v1/schema.json). The DB does **not** store the full envelope; the orchestrator persists a **denormalized workload slice** in **`payload_summary`**: `kind`, `name`, `image`, `gpu_count`, and `needs_ingress`, matching fields under **`WorkloadSpec`** in that schema (see `hammrly_orchestrator.persistence.repository.SubmissionRepository.record_received`). The query API types this JSON as **`PayloadSummary`** and **`WorkloadKind`** in code (`hammrly_query.contract_types`), and OpenAPI exposes the same enumerants as the contract’s **`WorkloadKind`**. **`HAMMRLY_INTERACTIVE_KINDS`** is validated against that enum at startup.

The query service uses **SQLAlchemy** in **read-only** mode: prefer a **replica** URL and/or PostgreSQL role with **`SELECT`** only. The engine optionally sets `default_transaction_read_only=on` on PostgreSQL connections (see `hammrly_query.session.create_engine_from_url`).

---

## 3. JWT authentication and authorization

Aligned with **gateway** (JWKS or dev **HS256**):

| Env (prefix `HAMMRLY_`) | Purpose |
|-------------------------|--------|
| `JWT_JWKS_URL` | OIDC JWKS (production) |
| `JWT_ISSUER`, `JWT_AUDIENCE` | Optional `iss` / `aud` verification |
| `JWT_DEV_HMAC_SECRET` | Dev-only HS256 secret |
| `JWT_REQUIRED_SCOPES` | Default **`hammrly:jobs:read`** (space/comma list) |
| `JWT_REQUIRE_SCOPE_CHECK` | Default `true` |
| `JWT_TENANT_CLAIM` | Default `hammrly_tenant_id` |
| `JWT_USER_ID_CLAIM` | Default `sub` → row filter `user_id` |

Missing/invalid token → **401** `unauthenticated`.  
Valid token but missing required scope → **403** `forbidden`.

---

## 4. Row scoping (authorization)

Every query applies:

1. **`submissions.user_id` = JWT user id** (`JWT_USER_ID_CLAIM` / `sub`).
2. If the JWT contains **`JWT_TENANT_CLAIM`**, results are additionally restricted to **`submissions.tenant_id`** matching that claim.
3. If **`HAMMRLY_CLUSTER_ID`** is set, only rows with **`submissions.cluster_id`** equal to that value are returned.

**404** is returned for “not found” when a **job_id** does not exist **or** the row would not pass the filters above (avoid leaking existence across users).

---

## 5. HTTP API (v1)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/jobs/{job_id}` | Single job detail + ordered **`events`** |
| `GET` | `/v1/me/jobs/interactive` | List **interactive** jobs for the caller |
| `GET` | `/v1/me/campaigns/{campaign_id}` | Headless **campaign summary** (`fail_count`, `fail_pct`, `by_status`, …) |
| `GET` | `/v1/me/campaigns/{campaign_id}/jobs` | Paginated jobs in a campaign (`status` filter, e.g. `failed`) |
| `GET` | `/v1/me/notifications` | In-app notification inbox (`unread_only`, pagination) |
| `GET` | `/v1/me/notifications/unread_count` | Cheap badge counter |
| `GET` | `/v1/me/notifications/stream` | **SSE** unread/latest bumps (Bearer via `fetch` stream; not native `EventSource`) |
| `POST` | `/v1/me/notifications/{id}/read` | Mark one notification read (`read_at`) |
| `POST` | `/v1/me/notifications/read_all` | Mark all unread notifications read |
| `GET` | `/.well-known/openapi.json` | OpenAPI document |
| `GET` | `/internal/openapi.json` | Same (FastAPI default) |
| `GET` | `/docs`, `/redoc` | Optional UI |
| `GET` | `/healthz` | Liveness |
| `GET` | `/readyz` | DB **`SELECT 1`** |

### 5.1 `GET /v1/jobs/{job_id}`

- **Path**: `job_id` is a UUID (gateway-issued).
- Success **200** with **`JobDetailResponse`** (submission columns + **`events`[]** sorted by `occurred_at` ascending).
- **404** `not_found` if missing or not visible to the caller.

**Lookup order:** PostgreSQL (scoped by JWT) first; if no row and **`HAMMRLY_REDIS_URL`** is set, fall back to the Redis **job index** (`hammrly:jobs:{job_id}`). Index hits return **200** with minimal detail (`events: []`, `status` of `pending` or `received`). Wrong owner → **404** (no existence leak).

**Interactive session polling (client contract)**

After gateway **`202 Accepted`** (`status: PENDING` on submit), clients SHOULD poll this endpoint until **`status == "ready"`**, then open **`access_url`**.

| Phase | `status` | `access_url` | Notes |
|-------|----------|--------------|--------|
| Pre-Postgres / index | **`pending`** | null | Redis index while orchestrator has not ingested |
| Provisional | `received` … `running` | May be set after Ingress create | Do not open yet |
| Openable | **`ready`** | Authoritative session URL | Emitted after pod readiness probe succeeds (`session_ready` event) |
| Terminal | `succeeded`, `failed`, … | May still be present | Session ended |

Recommended polling: exponential backoff starting at **1s**, cap **5s**, until `ready` or a terminal failure status. **404** after submit is rare when Redis is configured on query; retry briefly if query is Postgres-only.

Key **`events[]`** types: **`access_url_set`** (provisional URL persisted), **`session_ready`** (safe to open).

Gateway **`202 Accepted`** may include a **tentative** `access_url` when configured; always wait for Query **`status=ready`** before navigation.

### 5.2 `GET /v1/me/jobs/interactive`

Returns workloads whose **`payload_summary->>'kind'`** is one of (**configurable** via `HAMMRLY_INTERACTIVE_KINDS`, default `desktop,notebook,carta,contributed`). **`headless`** batch jobs are excluded.

**Query parameters**

- **`status`** (optional, repeatable) — when set, only return jobs whose `status` is one of the given values (e.g. `?status=ready&status=running` to exclude stale `unknown` rows)
- **`limit`** (default 50, max clamped by `HAMMRLY_LIST_MAX_LIMIT`)
- **`offset`** (default 0)

**Response**: `{ "items": [...], "limit", "offset" }` with summary fields plus extracted **`kind`** and nullable **`access_url`** (same URL as job detail; open when `status == "ready"`).

### 5.3 `GET /v1/me/campaigns/{campaign_id}`

Headless status UX (summary-first). Poll after gateway **`202`** (campaign row may appear shortly after orchestrator consumes the stream).

| Field | Notes |
|-------|--------|
| `fail_count` | From `campaigns.counts_json.failed` |
| `fail_pct` | `100 * fail_count / item_count` (1 decimal); `0.0` when `item_count` is 0 or unknown |
| `by_status` | Rollup counters per submission `status` |
| `progress_pct` | Terminal fraction of `item_count` |
| `failed_sample` | Up to 10 recent failed jobs |

### 5.4 `GET /v1/me/campaigns/{campaign_id}/jobs`

Paginated list; use `status=failed` for debugging. Not for full 100k exports.

### 5.5 Notifications (in-app)

Orchestrator writes **`user_notifications`** when a campaign reaches a Job-terminal rollup (one digest per campaign terminal status). Query exposes list/unread/SSE and marks `read_at`.

Campaign digests use `kind=campaign_terminal` with `body_json` containing `campaign_id`, `status`, `item_count`, `by_status`, `fail_count`, `fail_pct`, `failed_sample`, and `portal_path`.

SSE clients should use authenticated **`fetch`** streaming with `Authorization: Bearer` (native `EventSource` cannot set headers). Fallback: poll `unread_count`.

### 5.6 Future notification sinks (not implemented)

Same digest / `user_notifications` row is the source of truth. Deferred adapters:

| Sink | Intent | Notes |
|------|--------|-------|
| **Webhook** | User/tenant URL POST of digest JSON | Preferences + URL validation; Slack Incoming Webhook compatible |
| **Email** | One summary email per terminal campaign | Verified IdP email claim or prefs + SMTP |
| **Slack app** | Channel/DM via Slack API | Deferred (app install / API tokens) |
| **Web Push / SMS** | OS push or text | Not prioritized |

---

## 6. Configuration

| Variable | Purpose |
|----------|---------|
| `HOST`, `PORT` | Listen (default port **8081**) |
| `DATABASE_URL` | SQLAlchemy URL (**required** unless `SKIP_DB_BOOTSTRAP`) |
| `REDIS_URL` | Optional Redis for job-index fallback on `GET /v1/jobs/{job_id}` |
| `JOB_INDEX_REDIS_PREFIX` | Key prefix (default `hammrly:jobs:`) |
| `SKIP_DB_BOOTSTRAP` | Tests / custom wiring without engine |
| `CLUSTER_ID` | Optional multi-cluster filter |
| `INTERACTIVE_KINDS` | Comma list for interactive list |
| `LIST_DEFAULT_LIMIT`, `LIST_MAX_LIMIT` | Pagination caps |
| `JWT_*` | §3 |
| `CORS_ORIGINS` | Optional CORS |

---

## 7. Operations

- Run **beside** gateway on a different port or hostname.
- Point at the **same** database as orchestrator, preferably a **read replica** for SELECTs.
- Grant the query DB user **`SELECT`** on submissions/events/campaigns and **`SELECT`/`UPDATE`** on `user_notifications` (`read_at` only). Prefer no `INSERT`/`DELETE`.
- TLS terminates at ingress; service speaks HTTP internally.

---

## 8. Related documents

- Orchestrator persistence: [`services/orchestrator/SPEC.md`](../orchestrator/SPEC.md) §6
- Gateway (write path): [`services/gateway/SPEC.md`](../gateway/SPEC.md)
- Job contract (queue): [`contracts/job-submission/v1/README.md`](../../contracts/job-submission/v1/README.md)
