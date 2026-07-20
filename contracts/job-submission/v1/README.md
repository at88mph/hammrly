# Job submission contract (v1)

Canonical JSON Schema for queue messages from **gateway** to **orchestrator**: [schema.json](schema.json). Gateway HTTP implementation: [services/gateway/SPEC.md](../../services/gateway/SPEC.md).

Related validation and product rules: [VALIDATION.md](VALIDATION.md).

**Gateway-api** MUST generate **`job_id`** (required UUID) when creating the job resource, and **`submission_id`** for queue idempotency (see [VALIDATION.md](VALIDATION.md) identifiers section).

## `schema_version` policy

- Envelope field **`schema_version`** is a **`major.minor`** string (e.g. `1.0`), matching the JSON Schema `pattern` in [schema.json](schema.json).
- **Gateway-api** MUST publish only versions it implements (initially `1.0` or `1.1` as the contract evolves within major `1`).
- **Orchestrator** MUST:
  - **Accept** any `schema_version` whose **major** number matches the orchestrator’s supported major (e.g. accept all `1.x` for a v1 consumer).
  - **Reject** (DLQ / dead-letter, no `XACK`) messages whose **major** is unsupported (e.g. `2.0` while orchestrator only implements v1).
- **Minor** bumps MAY add optional fields; orchestrator SHOULD ignore unknown top-level keys only if explicitly allowed by policy (JSON Schema sets `additionalProperties: false` on the envelope — extend the schema for new fields rather than sending ad hoc keys). Examples: optional `workload.gpu_count` for NVIDIA GPU scheduling and optional `workload.input_uri` / `workload.output_uri` for workspace transfer.

## Redis Stream wire format

Default hammrly wire constants (override via service config if needed; keep stream key and `payload` field name stable across a deployment).

| Constant | Value | Notes |
|----------|--------|--------|
| Stream key | `hammrly:job-submissions` | `XADD` target for v1 submissions. |
| Message field name | `payload` | Single field per stream entry. Value is the **JSON serialization** of `JobSubmissionEnvelope` (UTF-8). Use one JSON object per entry; if your Redis client requires string values only, store the same document as a JSON string and parse on read. |
| Consumer group | `orchestrator` | Create with `XGROUP CREATE hammrly:job-submissions orchestrator $ MKSTREAM` (Redis 6+). |
| Consumer name | Unique per replica | e.g. pod UID or `hostname:pid`. |

**Publish (gateway)**

```text
XADD hammrly:job-submissions * payload <json-bytes>
```

**Consume (orchestrator)**

- `XREADGROUP GROUP orchestrator <consumer> BLOCK <ms> COUNT <n> STREAMS hammrly:job-submissions >`
- On success: `XACK hammrly:job-submissions orchestrator <id>`

**Dead-letter**

- Use a separate stream (e.g. `hammrly:job-submissions:dlq`) or agreed alternative; not part of this schema file.

## Job index (Redis string keys)

Separate from the submission **stream**: keyed lookup for Query during the ingestion window (gateway accept → orchestrator `record_received`).

| Constant | Default | Notes |
|----------|---------|--------|
| Key prefix | `hammrly:jobs:` | Full key: `{prefix}{job_id}` (`HAMMRLY_JOB_INDEX_REDIS_PREFIX`). |
| TTL | 86400 s | Config: `HAMMRLY_JOB_INDEX_TTL_SECONDS`. Keys expire naturally; orchestrator **updates in place** (never DEL on handoff). |

**Writers**

- **Gateway** (after validation, before `XADD`): `SET` with `"status": "pending"`.
- **Orchestrator** (after Postgres `record_received`): `SET` same key with `"status": "received"`, refresh TTL.

**Readers**

- **Query** `GET /v1/jobs/{job_id}`: Postgres first; on miss, `GET` index if `HAMMRLY_REDIS_URL` is configured.

**Value:** UTF-8 JSON:

```json
{
  "schema_version": "1.0",
  "job_id": "<uuid>",
  "submission_id": "<uuid>",
  "tenant_id": "<str>",
  "user_id": "<str>",
  "project_id": "<str|null>",
  "status": "pending | received",
  "requested_at": "<iso8601>",
  "queue_name": "<str|null>",
  "payload_summary": {
    "kind": "<str>",
    "name": "<str>",
    "image": "<str>",
    "gpu_count": 0,
    "needs_ingress": true
  }
}
```

## Layout

| Path | Purpose |
|------|---------|
| `schema.json` | JSON Schema 2020-12 for `JobSubmissionEnvelope` and nested `WorkloadSpec`. |
| `VALIDATION.md` | Cross-field rules (kind vs networking, ingress implies service, headless batch). |
| `README.md` | Versioning policy and Redis naming. |
