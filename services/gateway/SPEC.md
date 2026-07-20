# Gateway — specification

The **gateway** service is the **authenticated HTTP edge** for submitting Hammrly jobs. The primary client route is **`POST /v2/session`** (replacing a legacy HTTP session endpoint; unchanged queue contract). It validates **JWT** access tokens, enforces **authorization** to use the submission system, validates and normalizes requests into the **`JobSubmissionEnvelope`** contract ([`contracts/job-submission/v1/schema.json`](../../contracts/job-submission/v1/schema.json)), publishes to the **Redis Stream** consumed by the **orchestrator**, and returns identifiers to the client.

It does **not** run workloads, talk to Kubernetes, or own durable job lifecycle state (that belongs to the orchestrator / persistence tier).

---

## 1. Responsibilities

| Concern | Owner |
|---------|--------|
| JWT **authentication** (signature, `exp`, optional `iss` / `aud`) | gateway |
| **Authorization** (e.g. OAuth2-style `scope`) | gateway |
| **Tenant / user** mapping from token + JSON body policy | gateway |
| **JSON Schema** + cross-field validation ([`VALIDATION.md`](../../contracts/job-submission/v1/VALIDATION.md)) | gateway (reject), orchestrator (dead-letter if poison) |
| Generate **`job_id`** (UUID) | gateway |
| Choose **`submission_id`** (UUID); optional client **`Idempotency-Key`** | gateway |
| **`XADD`** envelope to Redis (`payload` field) | gateway |
| Consume stream, admit to cluster | orchestrator |

---

## 2. Trust boundaries

### 2.1 Client JSON body (`POST /v2/session`)

Accepted fields:

- **`workload`**: required — must satisfy [`WorkloadSpec`](../../contracts/job-submission/v1/schema.json) after envelope assembly.
- **`tenant_id`**: optional — required if the JWT does not carry a configured tenant claim (see §4).
- **`project_id`**: optional.
- **`correlation`**: optional — `trace_id`, `span_id`, `client_request_id` only (see schema).

**Ignored / rejected**: clients **must not** send `job_id`, `submission_id`, `user_id`, or `requested_at` to override security-critical envelope fields. The API model uses **`extra: forbid`** at the top level so unknown keys cause **400**.

### 2.2 Gateway-filled envelope fields

The gateway always sets:

- `schema_version` — from `HAMMRLY_SUBMISSION_SCHEMA_VERSION` (default `1.0`).
- `submission_id` — new UUID, or equal to **`Idempotency-Key`** when provided.
- `job_id` — new UUID per accepted submission attempt that reaches the queue.
- `user_id` — from JWT claim `HAMMRLY_JWT_USER_ID_CLAIM` (default `sub`).
- `requested_at` — gateway clock (RFC 3339 UTC).
- `tenant_id` — resolved per §4.

---

## 3. HTTP surface

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v2/session` | Create **interactive** session (publish job envelope to Redis) |
| `POST` | `/v2/campaigns` | Submit **headless** campaign (publish expansion envelope to Redis) |
| `GET` | `/.well-known/openapi.json` | **OpenAPI 3** document (stable discovery path) |
| `GET` | `/internal/openapi.json` | Same schema (FastAPI default mount) |
| `GET` | `/docs`, `/redoc` | Interactive docs (optional; disable in hardened prod if desired) |
| `GET` | `/healthz` | Liveness |
| `GET` | `/readyz` | Readiness (Redis **PING**) |

### 3.1 `POST /v2/session`

**Request headers**

- **`Authorization`**: `Bearer <JWT>` — **required**.
- **`Idempotency-Key`**: UUID string — optional. When set, it becomes **`submission_id`** and enables replay semantics (§7).

**Responses**

- **`202 Accepted`**: `{ "job_id": "<uuid>", "submission_id": "<uuid>", "status": "PENDING", "status_url": "<query-url>" }`. `status_url` points at the Query API job detail endpoint (default path `/v1/jobs/{job_id}`; absolute when `HAMMRLY_QUERY_PUBLIC_BASE_URL` is set). Poll until **`status == "ready"`**, then open **`access_url`** from the Query response (see query SPEC §5.1).
- **`400`**: invalid JSON, schema, or cross-field validation — `error=invalid_submission` (optional `details`).
- **`401`**: missing/invalid Bearer token — `error=unauthenticated`.
- **`403`**: token valid but not allowed to submit — `error=forbidden` (e.g. missing scope).
- **`409`**: same `Idempotency-Key` reused with **different** body — `error=idempotency_conflict`.
- **`503`**: Redis/XADD or idempotency contention — `error=queue_unavailable` or `idempotency_in_progress` (client may retry with backoff).

**Headless:** `workload.kind=headless` on `/v2/session` returns **`400`** with `error=use_campaign_submit`.

### 3.2 `POST /v2/campaigns`

**Scope:** All headless work (1 to many jobs). Contract: [`contracts/job-campaign/v1/`](../../contracts/job-campaign/v1/).

- **`Authorization`**: required.
- **`Idempotency-Key`**: optional UUID → becomes **`campaign_id`**.

**Responses**

- **`202 Accepted`**: `{ "campaign_id", "status": "accepted", "item_count", "status_url": "/v1/me/campaigns/{campaign_id}" }`.
- **`400`**: `invalid_campaign` or schema errors.
- **`409`**: idempotency conflict.

Gateway publishes to Redis stream **`hammrly:campaign-submissions`** (config: `HAMMRLY_CAMPAIGN_STREAM_KEY`). **No PostgreSQL.**

---

## 4. Authentication and authorization

### 4.1 Production path: asymmetric JWT (JWKS)

Configure:

- `HAMMRLY_JWT_JWKS_URL` — JWKS endpoint.
- `HAMMRLY_JWT_ISSUER` — if set, `iss` is verified.
- `HAMMRLY_JWT_AUDIENCE` — if set, `aud` is verified.

Algorithms accepted from JWKS: **RS256**, **ES256** (via PyJWT).

### 4.2 Development / tests: symmetric HS256

When **`HAMMRLY_JWT_DEV_HMAC_SECRET`** is set, the gateway decodes tokens with **HS256** using that secret and **does not** fetch JWKS. **Do not use in production** unless explicitly part of your threat model.

### 4.3 Scopes

When **`HAMMRLY_JWT_REQUIRE_SCOPE_CHECK=true`** (default), the token must contain every scope in **`HAMMRLY_JWT_REQUIRED_SCOPES`** (space- or comma-separated; default includes `hammrly:jobs:submit`) in the **`scope`** claim (space-separated string).

Set **`HAMMRLY_JWT_REQUIRE_SCOPE_CHECK=false`** only for emergency / lab setups.

### 4.4 Tenant resolution

Claim name: **`HAMMRLY_JWT_TENANT_CLAIM`** (default `hammrly_tenant_id`).

1. If the JWT contains a non-empty tenant claim, that value is **`tenant_id`**.
2. If the body also sends **`tenant_id`**, it **must match** when **`HAMMRLY_TENANT_MISMATCH_FORBIDDEN=true`** (default).
3. If there is **no** tenant claim, the body **must** include **`tenant_id`** when **`HAMMRLY_TENANT_BODY_ALLOWED=true`** (default).

Failure to resolve a tenant is **400** `invalid_submission` or **403** `forbidden` depending on the case (`tenant_mismatch` / `tenant_required_in_token`).

---

## 5. Validation

1. **Pydantic** parses the request body (forbid extras).
2. **Cross-field rules** ([`VALIDATION.md`](../../contracts/job-submission/v1/VALIDATION.md)) — e.g. `needs_ingress` ⇒ `needs_service`; interactive kinds expect service + ingress; resource sanity (CPU/memory or GPU).
3. **`jsonschema`** validates the **assembled envelope** against [`schema.json`](../../contracts/job-submission/v1/schema.json).

Schema path: **`HAMMRLY_CONTRACT_SCHEMA_PATH`** or auto-discovery from repository layout (see `hammrly_gateway.validation._default_contract_path`).

---

## 6. Queue publish and job index

- **Client**: `redis.asyncio` (TCP) or **`fakeredis`** when **`HAMMRLY_REDIS_FAKE=true`** (tests).
- **Command**: `XADD <HAMMRLY_REDIS_STREAM_KEY> * payload <utf8 json bytes>`.
- **Default stream key**: `hammrly:job-submissions` (must match orchestrator).
- **Job index** (before `XADD`): `SET hammrly:jobs:{job_id}` with JSON `status: pending` and TTL (`HAMMRLY_JOB_INDEX_TTL_SECONDS`). On `XADD` failure the index key is deleted. See [`contracts/job-submission/v1/README.md`](../../contracts/job-submission/v1/README.md) § Job index.

---

## 7. Idempotency

When **`Idempotency-Key`** is present (must be a **UUID**):

1. **`submission_id` = Idempotency-Key`**.
2. A **canonical SHA-256** of `{ tenant_id, project_id, correlation, workload }` (from the request) is stored with the result in Redis.
3. **Replay** with the same key and **same** hash: **202** with the **same** `job_id` / `submission_id` / `status: PENDING` — **no second XADD**.
4. Same key, **different** hash: **409** `idempotency_conflict`.
5. Parallel publishes use a short-lived Redis **`SET NX`** “claim” plus polling; conflicting waiters may see **503** `idempotency_in_progress` (retry).

Keys: prefix **`HAMMRLY_IDEMPOTENCY_REDIS_PREFIX`**, TTL **`HAMMRLY_IDEMPOTENCY_TTL_SECONDS`**.

---

## 8. Configuration reference (`HAMMRLY_*`)

| Variable | Purpose |
|----------|---------|
| `HOST`, `PORT` | Bind (`HAMMRLY_HOST`, `HAMMRLY_PORT`) |
| `REDIS_URL`, `REDIS_STREAM_KEY` | Redis + stream |
| `REDIS_FAKE` | In-memory Redis (tests) |
| `CONTRACT_SCHEMA_PATH` | Path to `schema.json` |
| `SUBMISSION_SCHEMA_VERSION` | Envelope `schema_version` |
| `JWT_*` | See §4 |
| `TENANT_*` / `TENANT_BODY_ALLOWED` / `TENANT_MISMATCH_FORBIDDEN` | §4.4 |
| `IDEMPOTENCY_*` | §7 |
| `JOB_INDEX_REDIS_PREFIX`, `JOB_INDEX_TTL_SECONDS` | Job index (§6) |
| `EPHEMERAL_STORAGE_DEFAULT`, `EPHEMERAL_STORAGE_MAX` | Default and maximum `workload.resources.ephemeral_storage` quantity in GB (`20` by default) |
| `CORS_ORIGINS` | Comma-separated origins; empty = no CORS |

---

## 9. Security notes

- Terminate **TLS** at ingress / load balancer; the app serves HTTP locally.
- Do **not** log raw JWTs or secrets.
- Prefer **JWKS** + short-lived access tokens in production.
- Rate limiting and WAF are **out of scope** for this package but recommended at the edge.

---

## 10. Related documents

- Queue wire format: [`contracts/job-submission/v1/README.md`](../../contracts/job-submission/v1/README.md)
- Validation matrix: [`contracts/job-submission/v1/VALIDATION.md`](../../contracts/job-submission/v1/VALIDATION.md)
- Orchestrator: [`services/orchestrator/SPEC.md`](../orchestrator/SPEC.md)
