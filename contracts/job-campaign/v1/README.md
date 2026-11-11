# Job campaign contract (v1)

Headless workloads are submitted only via **campaigns** (`POST /v2/campaigns`), not `POST /v2/session`.

| Document | Purpose |
|----------|---------|
| [schema.json](schema.json) | `CampaignSubmitRequest` (client → gateway) and `CampaignExpansionEnvelope` (gateway → Redis). |
| [VALIDATION.md](VALIDATION.md) | Cross-field rules, scale limits, input declaration, Kueue materialization. |

## Redis stream (campaign)

| Constant | Value |
|----------|--------|
| Stream key | `hammrly:campaign-submissions` |
| Field | `payload` — JSON `CampaignExpansionEnvelope` |
| Consumer group | `orchestrator` (campaign expander) |

Single interactive jobs continue to use [`hammrly:job-submissions`](../job-submission/v1/README.md).

## Kueue and cluster materialization

Hammrly requires **[Kueue](https://kueue.sigs.k8s.io/)** and the **[JobSet](https://jobset.sigs.k8s.io/)** controller.

The **client contract is unchanged**: one campaign submit, ordered `items` or `manifest_uri`.

The orchestrator creates **one suspended JobSet per campaign** with an indexed child `Job` (`completions = len(items)`, including **`len(items) == 1`**). Per-item rows in Postgres/query are unchanged; Kueue admits the JobSet using `kueue.x-k8s.io/queue-name` on **JobSet metadata**. See [VALIDATION.md](VALIDATION.md) § Campaign scope.

## `schema_version`

Same policy as job-submission v1: gateway publishes `1.0`; orchestrator accepts matching major.
