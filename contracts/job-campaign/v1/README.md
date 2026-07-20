# Job campaign contract (v1)

Headless workloads are submitted only via **campaigns** (`POST /v2/campaigns`), not `POST /v2/session`.

| Document | Purpose |
|----------|---------|
| [schema.json](schema.json) | `CampaignSubmitRequest` (client → gateway) and `CampaignExpansionEnvelope` (gateway → Redis). |
| [VALIDATION.md](VALIDATION.md) | Cross-field rules, scale limits, naming vs `kind_options.batch`. |

## Redis stream (campaign)

| Constant | Value |
|----------|--------|
| Stream key | `hammrly:campaign-submissions` |
| Field | `payload` — JSON `CampaignExpansionEnvelope` |
| Consumer group | `orchestrator` (campaign expander) |

Single interactive jobs continue to use [`hammrly:job-submissions`](../job-submission/v1/README.md).

## Kueue JobSet

**Out of scope.** Campaigns expand to **N independent `batch/v1` Job** objects with `kueue.x-k8s.io/queue-name` labels—not JobSet CRDs.

## `schema_version`

Same policy as job-submission v1: gateway publishes `1.0`; orchestrator accepts matching major.
