# Job campaign validation (v1)

Cross-field rules for [schema.json](schema.json). Workload template rules also follow [job-submission VALIDATION](../job-submission/v1/VALIDATION.md) (headless networking, resources, workspace URIs).

## Campaign vs `kind_options.batch`

| Term | Meaning |
|------|---------|
| **campaign** | A submission group: one HTTP submit, N expanded Kubernetes Jobs. |
| **`kind_options.batch`** | Container entrypoint / Job parallelism for a single headless pod—unrelated to campaign grouping. |

## Submit path

- **`POST /v2/campaigns` only** for `template.kind: headless`.
- **`POST /v2/session`** MUST reject `workload.kind: headless` with error `use_campaign_submit`.

## Items vs manifest

| Rule | Detail |
|------|--------|
| Exactly one | `items` **or** `manifest_uri` |
| Inline `items` | `len(items) >= 1`; `len(items) <= HAMMRLY_CAMPAIGN_MAX_INLINE_ITEMS` (gateway, default 10000) |
| Large campaigns | Use `manifest_uri` only; do not embed ~100k items in HTTP or Redis payload |
| `item_key` | Unique within campaign; charset `^[A-Za-z0-9][A-Za-z0-9._-]*$` |
| `input_uri` | Required on each item unless template supplies a shared input (unusual) |

Manifest formats (orchestrator):

- JSONL: one `CampaignItem` per line
- JSON: `{ "items": [ ... ] }`

## Template merge (expansion)

Per item, orchestrator builds `JobSubmissionEnvelope.workload`:

1. Start from normalized `template`.
2. Apply `campaign.output_uri` / per-item `output_uri` with placeholders `{campaign_id}`, `{item_key}`, `{project_id}`.
3. Set `input_uri` from item.
4. If item `batch_args` set: **replace** `kind_options.batch.args`; else keep template args.
5. Merge `campaign.labels` then item `labels` onto workload labels.
6. Optional item `name` overrides `template.name`.

## Kueue

Each expanded Job is a standard suspended Job with `kueue.x-k8s.io/queue-name` from orchestrator config for `headless`. **No JobSet.**
