# Job campaign validation (v1)

Cross-field rules for [schema.json](schema.json). Workload template rules also follow [job-submission VALIDATION](../job-submission/v1/VALIDATION.md) (headless networking, resources, workspace URIs).

## Campaign vs `kind_options.batch`

| Term | Meaning |
|------|---------|
| **campaign** | A submission group: one HTTP submit, N logical jobs in metadata; **one JobSet** in the cluster (see Kueue). |
| **`kind_options.batch`** | Container entrypoint / Job parallelism for a single headless pod—unrelated to campaign grouping. |

## Campaign scope

- **One submit, one JobSet:** every headless batch goes through `POST /v2/campaigns`, including **a single input** (`items` length 1 → JobSet with `completions: 1`). There is no separate “one-off headless Job” API.
- **Domain-agnostic:** items are arbitrary work units (files, shards, parameter rows, etc.) sharing one `template` image and resources. Contract examples use generic names only—they are not tuned to a particular science or file format.
- **Scale:** `parallelism` and `ephemeral_storage` follow the **template** and cluster policy, not a specific workload type.

## Input declaration

Inputs are **declared**, not mounted. Each execution unit copies **one** `input_uri` into `/workspace/inputs` on ephemeral disk before the workload starts. See also [job-submission workspace rules](../job-submission/v1/VALIDATION.md).

| Surface | Rule |
|---------|------|
| `items[].input_uri` | Required per item unless `template.input_uri` supplies a shared object (unusual). |
| Order | **Significant**: manifest/array index `i` maps to JobSet completion index `i`. |
| `items[].input_bytes` | Optional; gateway may reject when `template.resources.ephemeral_storage` (GB) is smaller than the implied size. |
| Credentials | Pre-signed HTTPS or cluster-reachable URLs; no platform storage secrets in v1. |
| Staging | Init container download; schemes per job-submission workspace rules (`http`, `https`, `file`, local). |

Example item:

```json
{
  "item_key": "shard-7",
  "input_uri": "https://data.example/bucket/run-42/shard-7.dat?X-Amz-Signature=...",
  "batch_args": ["--input", "/workspace/inputs/shard-7.dat"]
}
```

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
| `input_uri` | Required on each item unless template supplies a shared input (unusual); see § Input declaration |

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

| Admission unit | Queue label |
|----------------|-------------|
| One **JobSet** per campaign (indexed child Job) | `kueue.x-k8s.io/queue-name` on **JobSet** metadata (headless LocalQueue from orchestrator config) |

`template.kind_options.batch.parallelism` caps concurrent indexed pods. Size ClusterQueue quota for **(init + workload + sidecar) requests × parallelism**.
