# Orchestrator Service — Specification

## 1. Purpose and scope

The **Orchestrator** is the runtime worker that bridges **submission intent** (from the API gateway, via a queue) and **cluster execution** (Kubernetes `Job` objects admitted and scheduled by [Kueue](https://kueue.sigs.k8s.io/)). It is responsible for:

- Consuming durable submission requests from a **running queue** (default assumption: **Redis**).
- Creating and updating **Kubernetes `Job`** resources in a **suspended** state so **Kueue** can order admission and unsuspend work according to quotas and priorities.
- Maintaining an **authoritative external store of job metadata and lifecycle state** so operators and the **gateway** can list, filter, and answer questions about runs **without** treating the Kubernetes API as the primary database.

**Out of scope** (owned by other services):

- Public HTTP API and authn/authz for end users (**gateway**).
- Interactive UX (**user-interface**).
- Defining batch workloads beyond the contract agreed with the gateway (orchestrator validates and maps an agreed schema).

---

## 2. Goals and non-goals

### Goals

- **At-least-once** processing from the queue with **idempotent** Kubernetes creates and **deduplicated** metadata writes.
- **Decoupled scaling**: orchestrator replicas scale horizontally; the queue provides backpressure and redelivery semantics.
- **Kueue-first scheduling**: Jobs enter the cluster **suspended**; Kueue controls when they become runnable.
- **Queryable job history and status** from a **non-Kubernetes** datastore optimized for list/detail/filter and operational dashboards.

### Non-goals

- Using etcd / the Kubernetes API as the **only** source of truth for “what jobs exist and their business state” (Kubernetes remains the source of truth for *pod-level* execution reality; the datastore mirrors *submission and orchestration* state).
- Implementing a full workflow engine (DAGs, steps, retries beyond simple Job semantics) unless later extended explicitly.

---

## 3. High-level architecture

```text
gateway ──publish──▶ Redis queue ──consume──▶ Orchestrator
                              │                     │
                              │                     ├──▶ Metadata store (PostgreSQL, etc.)
                              │                     │
                              └── (optional DLQ)     └──▶ Kubernetes API (Job, suspend=true)
                                                          └──▶ Kueue (admits / unsuspends)
```

**Components:**

1. **Queue consumer** — long-running loop(s) that claim messages, process them, and acknowledge or requeue.
2. **Kubernetes writer** — builds `Job` specs, applies suspend semantics, applies labels/owner references for correlation.
3. **Metadata service layer** — repository abstraction over the persistent store; transaction boundaries aligned with “accepted submission” vs “cluster object created”.
4. **(Recommended) Kubernetes informer / watch** — optional-but-valuable for reconciling **observed** cluster state (start time, completion, failures) into the metadata store without polling `kubectl`-style from user-facing APIs.

---

## 4. Queue design (Redis)

### 4.1 Recommended primitive

Prefer **Redis Streams** per consumer group for:

- Consumer groups and **pending-entry** recovery (crash safety).
- Approximate ordering and replay by ID.
- Acknowledgement via `XACK`.

Alternative: **Redis Lists** (`BRPOPLPUSH` + reliability bookkeeping) — simpler but weaker replay and visibility. **Streams are the default** in this spec.

### 4.2 Message envelope (logical contract)

Messages are **versioned JSON** documents validated by the canonical schema at [`contracts/job-submission/v1/schema.json`](../../contracts/job-submission/v1/schema.json). Cross-field product rules (e.g. interactive kinds vs networking flags) live in [`contracts/job-submission/v1/VALIDATION.md`](../../contracts/job-submission/v1/VALIDATION.md).

#### Envelope fields

| Field | Description |
|--------|-------------|
| `schema_version` | Contract version (`major.minor`). Acceptance policy: same **major** as orchestrator-supported release. See [`contracts/job-submission/v1/README.md`](../../contracts/job-submission/v1/README.md). |
| `submission_id` | **Queue idempotency key** (UUID from gateway). Stable across retries of the same submission. |
| `job_id` | **Gateway-generated job id** (UUID); API- and metadata-facing. Label **`hammrly.io/job-id`**. |
| `tenant_id` | Required isolation / quota scope (maps to Kueue `LocalQueue` or labels). |
| `user_id` | Required end-user identity for audit and **Kubernetes** labeling; orchestrator maps to label `hammrly.io/user-id` (value MUST be label-safe; see [VALIDATION.md](../../contracts/job-submission/v1/VALIDATION.md)). |
| `project_id` | Optional grouping or sub-scope. |
| `requested_at` | RFC 3339 timestamp from gateway. |
| `correlation` | Optional: `trace_id`, `span_id`, `client_request_id`. |
| `workload` | **WorkloadSpec** — see below (replaces the earlier `job_template` name to avoid confusion with Kubernetes `Job.spec.template`). |

#### Workload (`workload`)

| Field | Description |
|--------|-------------|
| `kind` | One of: **`desktop`** (NoVNC), **`notebook`** (Jupyter), **`carta`**, **`contributed`** (user image, interactive), **`headless`** (batch). |
| `name` | Logical workload name; sanitizable to RFC 1123; unique Kubernetes naming derived in orchestrator (e.g. via `submission_id`). |
| `image` | OCI image reference. |
| `gpu_count` | Optional non-negative integer — NVIDIA GPU count. Orchestrator sets device resources and schedules **on** GPU worker nodes when `> 0`, and **off** those nodes when `0` or omitted (unless legacy `resources.nvidia.com/gpu` is set). Label defaults: `skaha.opencadc.org/node-type=gpu-worker-node` (configurable). |
| `resources` | Kubernetes resource quantity map (`cpu`, `memory`, optional accelerators, `ephemeral_storage`, etc.). Each value is applied as both request and limit. Callers set `ephemeral_storage` in GB; the orchestrator defaults to 20GB and caps by deployer configuration. |
| `needs_ingress` | If true, orchestrator creates an **Ingress** (requires `needs_service` in normal patterns). |
| `needs_service` | If true, orchestrator creates a **Service**. |
| `priority` | Optional; Kueue / label mapping. |
| `labels` / `annotations` | Optional passthrough (no secrets). |
| `volumes` | Optional; platform may restrict shapes. |
| `ttl_seconds_after_finished` | Optional Job TTL hint. |
| `kind_options` | Discriminated by `kind` (e.g. `novnc`, `jupyter`, `carta`, `contributed`, **`batch` required for `headless`**). |

The **gateway** and **orchestrator** MUST use this shared contract (schema + validation matrix).

#### 4.2.1 Redis stream fields

Wire layout for **`XADD` / `XREADGROUP`** is defined in [`contracts/job-submission/v1/README.md`](../../contracts/job-submission/v1/README.md) (stream key `hammrly:job-submissions`, field `payload`, consumer group `orchestrator`).

### 4.3 Processing semantics

- **Claim**: `XREADGROUP` with reasonable block timeout; process one message at a time per worker thread unless parallelism is carefully designed.
- **Ack**: `XACK` only after:
  - metadata row reaches a durable “accepted” or “submitted_to_cluster” state, **and**
  - Kubernetes create succeeded (or duplicate create was detected and treated as success).
- **Failures**: 
  - Transient errors (API timeout): leave message pending or explicit retry with backoff (implementation choice: reclaim pending via `XAUTOCLAIM` or move to retry stream).
  - Poison / bad payload: move to a **dead-letter stream** or list with reason; record failure in metadata.

### 4.4 Idempotency

- **Primary key** in metadata: `submission_id`.
- **Kubernetes**: use deterministic naming OR store `job_uid` / `job_name` after first successful create; on retry, skip create if row already bound to a live `Job`.
- Optional: hash of normalized `workload` (or full envelope) stored to detect conflicting retries with same `submission_id`.

---

## 5. Kubernetes integration

### 5.1 Job specification

- Create a **`batch/v1` `Job`** with **`spec.suspend: true`** (supported in modern Kubernetes for Job suspension) using the official **[kubernetes-client/python](https://github.com/kubernetes-client/python)** package in the reference implementation.
- Labels (minimum):
  - `hammrly.io/submission-id=<submission_id>`
  - `hammrly.io/job-id=<job_id>`
  - `hammrly.io/tenant-id=<tenant_id>`
  - `hammrly.io/user-id=<normalized_user_id>` (from envelope `user_id`, normalized per [VALIDATION.md](../../contracts/job-submission/v1/VALIDATION.md))
  - **`kueue.x-k8s.io/queue-name=<LocalQueue name>`** — value is chosen by the **orchestrator** from **`workload.kind`** and **`HAMMRLY_KUEUE_*`** settings (per-kind overrides and **`HAMMRLY_KUEUE_LOCAL_QUEUE_DEFAULT`**). Not part of the submission envelope. See [Kueue labels](https://kueue.sigs.k8s.io/docs/reference/labels-and-annotations).
  - `hammrly.io/managed-by=orchestrator` — scopes **list/watch** and drift reconciler to orchestrator-created Jobs.
  - `hammrly.io/workload-kind=<kind>` (reference implementation)
  - Additional queue / priority labels per cluster policy if required by your Kueue version.

**Pod template:** **`spec.template.metadata.labels`** carries the **same** label set as the Job so every Pod retains **user** and **job** identity (and `managed-by`) for selectors and observability. Workload pod/container security contexts require non-root execution with fixed UID/GID, privilege escalation disabled, all Linux capabilities dropped, and `RuntimeDefault` seccomp.

### 5.2 Headless campaigns

- Gateway publishes **`CampaignExpansionEnvelope`** to **`hammrly:campaign-submissions`** ([`contracts/job-campaign/v1/`](../../contracts/job-campaign/v1/)).
- Orchestrator **campaign expander** inserts `campaigns`, then one **`submissions` row + suspended Job** per item (label `hammrly.io/campaign-id`).
- Large campaigns use **`manifest_uri`** (JSONL); inline **`items`** capped by `HAMMRLY_CAMPAIGN_MAX_INLINE_ITEMS` on gateway.

### 5.3 Kueue

- Orchestrator **does not** unsuspend Jobs manually in the steady state; **Kueue** admits work per `LocalQueue` / `ClusterQueue` configuration.
- **JobSet is out of scope:** embarrassingly parallel headless work uses **N plain `batch/v1` Job** objects, not JobSet CRDs.
- Orchestrator MUST ensure each Job is **eligible** for Kueue:
  - Correct labels / resource requests / queue affinity as defined in platform policy.
  - Optional: create or reference the Kueue **`Workload`** object if the deployment uses explicit Workload objects versus plain Job integration — **this must match the cluster’s Kueue version and config**.

### 5.4 RBAC and tenancy

- Run orchestrator with a **dedicated ServiceAccount**.
- **Prefer** one namespace per tenant OR strong label selectors + RBAC; avoid cluster-admin.
- **Secrets**: never copy secret material into the metadata DB; reference Kubernetes `Secret` names or external secret stores.

### 5.5 Resource lifecycle

- `ttlSecondsAfterFinished` or policy controller cleans finished Jobs in-cluster; **metadata retention** is governed by the external store (see §7).

---

## 6. Metadata persistence (avoid Kubernetes as the query database)

### 6.1 Principle

**Kubernetes** answers: “What is running *right now* in this cluster, and what did the pods do?”

The **metadata store** answers: “What did users submit, across restarts and clusters? What is the business status? What queue/priority? What errors were surfaced to the platform?”

This separation avoids expensive `kubectl`/`API` list queries for UX and keeps history even after objects are garbage-collected.

### 6.2 Recommended technology

**PostgreSQL** (or another relational DB) as the default:

- Strong consistency for idempotency and status transitions.
- Flexible indexing for listing by tenant, status, time range, queue.

For very early prototypes, **SQLite** could stand in locally; production should assume **managed PostgreSQL**.

### 6.3 Logical data model (illustrative)

**Table: `submissions`** (one row per `submission_id`)

| Column | Notes |
|--------|------|
| `submission_id` | PK, UUID (queue idempotency / ingestion key) |
| **`job_id`** | Unique (indexed); gateway-issued id for API/UI and `hammrly.io/job-id` label |
| `tenant_id`, `project_id`, **`user_id`** | Filtering; mirror envelope for list-by-user |
| `status` | Enum: `received`, `building_spec`, `submitted_to_cluster`, `admitted`, `running`, **`ready`**, `succeeded`, `failed`, `cancelled`, `dead_letter` |
| `status_detail` | Human-readable last error or phase |
| `queue_name` | Resolved Kueue LocalQueue applied to the Job (from orchestrator config + `kind`); not from client payload. |
| `priority` | Integer or class |
| **`gpu_count`** | GPUs requested (`0` = CPU-only scheduling policy applies). |
| `k8s_job_name`, `k8s_namespace`, `k8s_job_uid` | Bind after create |
| `cluster_id` | If multi-cluster later |
| `k8s_resource_version` | Last applied Kubernetes `metadata.resourceVersion` (watch idempotency). |
| `redis_stream_message_id` | Optional Redis message id for support / replay correlation. |
| `requested_at`, `created_at`, `updated_at` | Timestamps |
| `template_hash` | Optional integrity check |
| `payload_redacted_json` | Optional small summary — **avoid storing secrets** |

**Table: `submission_events`** (append-only audit / timeline)

| Column | Notes |
|--------|------|
| `id` | Bigserial |
| `submission_id` | FK |
| `event_type` | e.g. `queued`, `k8s_create_ok`, `access_url_set`, **`session_ready`**, `k8s_create_err`, `watch_running`, … |
| `payload_json` | Small diagnostic blob |
| `occurred_at` | Timestamp |

**Optional: `worker_claims`** for debugging inflight work (message ID, worker instance).

### 6.4 Who writes what

| Event | Writer | Notes |
|--------|--------|--------|
| Message received (valid envelope) | Orchestrator | `queued` / `redelivered` |
| Before Kubernetes create | Orchestrator | `building_spec` |
| Job created in API | Orchestrator | `k8s_create_ok` |
| Job create failure | Orchestrator | `k8s_create_err` |
| Watch: phase change | Orchestrator (Job watch thread) | `watch_*` with condition/count payloads |
| Workload error manifest | Orchestrator (Job watch + pod log scrape) | `workload_error`; sets `status_detail` to `"{code}: {message}"` |
| Watch: Job deleted | Orchestrator | `job_deleted` |
| Drift: Job missing in cluster | Orchestrator (periodic LIST) | `cluster_job_missing` |
| Campaign Job-terminal rollup | Orchestrator | Campaign `completed` / `partial_failed` / `failed` when all items terminal; one `user_notifications` digest |
| Gateway user cancellation | Future | — |

### 6.5 Reconciliation and drift

A lightweight **reconciler** loop (or informer-driven updates) SHOULD:

- Periodically ensure `submissions` rows for recent active work still match cluster `Job` existence (optional, for incidents).
- Mark `unknown` if cluster object disappeared unexpectedly (node loss, manual delete) while business policy expects it to exist.

Exact reconciler frequency is an operational concern (e.g. every few minutes for active IDs only).

### 6.6 Query access

- **Query service**: reference HTTP implementation [`services/query/SPEC.md`](../query/SPEC.md). Prefer a **PostgreSQL read replica** / **`SELECT`** role for submissions, events, and campaigns. Query may **`UPDATE`** `user_notifications.read_at` for inbox UX (writable engine path).
- **gateway** may read from the same store (replica optional) instead of calling the Kubernetes API for list/detail.
- **orchestrator** is the **only** writer for automated lifecycle fields and notification inserts (except admin tooling).

---

## 7. Observability

- **Structured logs** with **`job_id`**, `submission_id`, `tenant_id`, **`user_id`**, message ID, Kubernetes UID.
- **Metrics**: queue lag, processing latency, K8s API error rate, DB transaction failures, Job creation rate by queue.
- **Tracing**: propagate W3C trace context from gateway message into spans around queue read, DB commit, and K8s apply.

---

## 8. Configuration (environment)

Representative settings:

- Redis URL, stream name, consumer group, consumer name prefix.
- `HAMMRLY_DATABASE_URL` (required), `HAMMRLY_CLUSTER_ID`
- `HAMMRLY_JOB_WATCH_ENABLED`, `HAMMRLY_JOB_WATCH_NAMESPACE`, `HAMMRLY_JOB_WATCH_LABEL_SELECTOR`, `HAMMRLY_JOB_WATCH_TIMEOUT_SECONDS`, `HAMMRLY_JOB_DRIFT_RECONCILE_INTERVAL_SEC`
- Kubernetes kubeconfig / in-cluster config; target namespace(s).
- Feature flags: dry-run (parse + DB only), max retries, DLQ stream name.
- **Cluster identity** (`cluster_id`) for multi-cluster futures.

Migrations: run `alembic upgrade head` from this directory with `PYTHONPATH=src` and `HAMMRLY_DATABASE_URL` set (see [README](README.md)).

---

## 9. Deployment model

- ** StatefulSet or Deployment** with **horizontal** scaling; Redis stream consumer group divides partitions across instances.
- **Leader election** only if any subsystem requires single-writer semantics beyond stream partitioning (prefer designs that avoid global leader).
- **PodDisruptionBudget** and graceful shutdown: finish in-flight message or return to pending before exit.

---

## 10. Security

- mTLS or private network between orchestrator, Redis, and PostgreSQL.
- Vault / KMS for DSNs; no secrets in logs.
- Validate job templates for **unsafe** image registries or disallowed volume types per policy (defense in depth with admission controllers).

---

## 11. Open decisions (to resolve during implementation)

1. **Exact Kueue integration shape** for your cluster version (labels-only Job vs Workload CRD).
2. **Multi-tenancy model**: namespace-per-tenant vs shared namespace with RBAC and synthetic prefixes.
3. **Cancellation** semantics and whether it is queue-driven or synchronous API.
4. **Payload storage**: full blob in DB vs object store (S3/MinIO) with pointer in DB for large specs.

---

## 12. Implementation checklist (non-binding)

- [x] Define shared **message schema** with gateway (see `contracts/job-submission/v1/`).
- [ ] Redis Streams consumer with idempotent processing + DLQ (initial listener: [`README.md`](README.md)).
- [ ] Implement PostgreSQL schema + migrations.
- [ ] Implement Kubernetes Job builder (`suspend: true`) + bounded RBAC (initial submitter: [`src/hammrly_orchestrator/k8s/`](src/hammrly_orchestrator/k8s/); uses **kubernetes-client/python** and **`kueue.x-k8s.io/queue-name`**).
- [ ] Add Job informer for completion / failure → DB updates.
- [ ] Add metrics, health endpoints (`/healthz`, `/readyz`), and rollout documentation.

---

*Version: 0.1 — planning draft aligned with hammrly monorepo layout.*
