---
name: kueue-development
description: Guides Hammrly's Kueue workload admission integration—suspended batch/v1 Jobs, kueue.x-k8s.io/queue-name labels, LocalQueue routing by workload.kind, quota-facing resource requests, and distinguishing Job watch status from Kueue admission. Use when changing queue mapping, admission eligibility, campaign parallelism, cluster queue policy alignment, troubleshooting pending Jobs, or extending Kueue CRD access. For V1Job/V1Pod construction use the kubernetes-development skill.
---

# Kueue development (Hammrly)

**Scope:** How Hammrly **uses** Kueue on the cluster. Cluster install (Kueue version, `ClusterQueue`, `ResourceFlavor`, cohorts) is **platform/ops**; this repo configures **application-side eligibility** and **observability proxies**.

**Kubernetes object construction** (Job suspend, pod resources, labels on `V1Job`): follow the [`kubernetes-development`](../kubernetes-development/SKILL.md) skill — do not duplicate that guidance here.

**Authoritative app behavior:** [`services/orchestrator/SPEC.md`](../../../services/orchestrator/SPEC.md) §5.1–5.3, [`contracts/job-submission/v1/VALIDATION.md`](../../../contracts/job-submission/v1/VALIDATION.md) (Kueue + resources), [`contracts/job-campaign/v1/README.md`](../../../contracts/job-campaign/v1/README.md) (no JobSet).

## Deployed Kueue version (not in this repo)

This repository **does not pin or chart-install Kueue**. There is no `CustomObjectsApi` usage for Kueue CRDs in application code today.

Before changing integration or reading API shapes:

1. Record the **Kueue controller version** running on the target cluster (e.g. deployment image tag in `kueue-system` or your install manifest).
2. Use **that version’s** docs on [kueue.sigs.k8s.io](https://kueue.sigs.k8s.io/) (concepts, APIs, labels, troubleshooting).
3. Confirm CRD **served versions** on the cluster: `kubectl api-resources | grep kueue` (group is typically **`kueue.x-k8s.io`**; exact resource versions vary by release).

Do not assume a Kueue minor version from Hammrly’s `kubernetes` Python client version (`kubernetes>=28` in orchestrator only covers core/batch/networking APIs).

## Architecture: what Hammrly implements vs what Kueue owns

| Layer | Owner | In this codebase |
|-------|--------|-------------------|
| **Admission & quota** | Kueue (`LocalQueue` → `ClusterQueue`, flavors, cohorts) | Not configured here; cluster policy must match pod resource requests |
| **Workload object** | Kueue (often auto-derived from labeled suspended `Job`) | Orchestrator does **not** create/patch `Workload` CRDs |
| **Job create** | Orchestrator | `V1Job` with `spec.suspend=true`, queue label, full pod template |
| **Unsuspend / run** | Kueue | Orchestrator **must not** set `suspend=false` in steady state (SPEC §5.3) |
| **Job/Pod lifecycle UI status** | Orchestrator + DB | `job_watch` maps **`batch/v1` Job** fields only |
| **Session ready** | Orchestrator | `pod_watch` on Ready probes — **after** Kueue has admitted and pods schedule |

```text
Envelope → KubernetesSubmitter → suspended Job (+ labels)
                                      ↓
                               Kueue admits / unsuspends
                                      ↓
                               Pods run → job_watch / pod_watch → PostgreSQL status
```

**JobSet:** **out of scope.** Campaigns and parallel headless work use **N independent `batch/v1` Job** objects, each with its own queue label ([`job-campaign` README](../../../contracts/job-campaign/v1/README.md)).

## Application integration (current)

### Queue selection (LocalQueue name)

| Source | Mechanism |
|--------|-----------|
| Contract / client JSON | **Does not** carry LocalQueue name |
| Orchestrator | Label **`kueue.x-k8s.io/queue-name`** on Job and pod template (`KUEUE_LOCAL_QUEUE_LABEL` in [`labels.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/labels.py)) |
| Resolution | `Settings.kueue_local_queue_for_workload_kind(kind)` — per-kind `HAMMRLY_KUEUE_QUEUE_*` env, else `HAMMRLY_KUEUE_LOCAL_QUEUE_DEFAULT` |
| Helm | `orchestrator.session.kueue.localQueueDefault`, `session.kinds.<kind>.queueName` → env vars ([`helm/orchestrator/templates/deployment.yaml`](../../../helm/orchestrator/templates/deployment.yaml)) |
| Persistence | `submissions.queue_name` at receive time (same resolved string; audit, not re-read from cluster) |

LocalQueue **objects must exist** in the workload namespace (or as your cluster’s Kueue config dictates). Wrong or missing names → Jobs stay suspended and Kueue reports inadmissibility — see [troubleshooting](reference.md#troubleshooting-pending-and-inadmissible-work).

### Suspended Job pattern

- `V1JobSpec(suspend=True)` on create ([`submitter.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/submitter.py)).
- Requires a Kubernetes version and Kueue configuration that support **Job suspension** integration (per your deployed Kueue docs).

### JobSet

- Treat JobSet as a Kubernetes custom resource.
- Follow the installed JobSet API version and specification.
- Understand its relationship to underlying Jobs, replicated Jobs,
  and Pods.
- Consult official JobSet documentation when implementing or
  modifying JobSet resources.

### Resource requests Kueue sees

Admission uses the **Pod template** resource requests (init + workload + sidecar containers):

- Contract `workload.resources` → equal **request and limit** per key ([`resource_map_to_requirements`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/pod_spec.py), VALIDATION.md).
- Keys include `cpu`, `memory`, `ephemeral-storage` (via policy), and `nvidia.com/gpu` when `gpu_count` > 0.
- **ClusterQueue** quotas and **ResourceFlavor** node labels must cover these requests (e.g. GPU flavors vs `k8s_gpu_node_label_*` affinity).

Changing quotas or flavors is cluster config; changing **what Jobs request** is orchestrator/`pod_spec` work → `kubernetes-development`.

### Priority and tenant → queue

- `workload.priority` is stored on `submissions.priority` but **is not** mapped to Kueue priority labels/classes in the current submit path (SPEC allows future “additional queue / priority labels per cluster policy”).
- `tenant_id` is a product/isolation field; **queue routing today is by `workload.kind`**, not tenant. Per-tenant LocalQueues require ops mapping (separate LocalQueues + env overrides or future code).

## Kubernetes Job status vs Kueue admission

Orchestrator **does not** watch Kueue `Workload` objects. [`map_job_to_submission_status`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/job_state.py) infers platform status from **Job** state:

| Job signal | `submissions.status` (approx.) |
|------------|--------------------------------|
| `spec.suspend==true`, no active pods | `submitted_to_cluster` (queued behind Kueue) |
| `spec.suspend==false`, no active pods yet | `admitted` (Kueue unsuspended; scheduling) |
| `status.active > 0` | `running` |
| Complete / Failed conditions | `succeeded` / `failed` |

A Job can be **suspended with quota available** but not yet processed — still `submitted_to_cluster`. **Inadmissible** workloads (quota, flavors, queue mismatch) often remain suspended with no orchestrator-specific error until ops inspect Kueue; do not conflate with Kubernetes Job `Failed` before pods start.

Watch payload includes `suspend` and condition summaries ([`watch_event_payload`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/job_state.py)) for timeline/audit.

## Kueue concepts (cluster-side; align app requests with policy)

Use official Kueue docs for the **deployed version**. Hammrly developers typically touch these indirectly:

1. **LocalQueue** — named by `kueue.x-k8s.io/queue-name`; entry point for a namespace.
2. **ClusterQueue** — quota, flavor assignment, preemption policy for one or more LocalQueues.
3. **ResourceFlavor** — ties quotas to node labels/taints (relate to orchestrator GPU label settings).
4. **Cohort** — fair sharing across ClusterQueues (ops design).
5. **Workload** — Kueue’s unit of admission; may be managed automatically from integrated `Job` objects.

**Preemption / lifecycle:** governed by ClusterQueue and Workload policies on the cluster. Hammrly’s job watch treats terminal Job conditions like any other failure/success; it does not implement preemption logic.

## Python client and Kueue CRDs

- **Today:** no `CustomObjectsApi` calls for `kueue.x-k8s.io/*` in orchestrator.
- **If adding** (e.g. read `Workload` status, explicit Workload create per cluster policy):
  - Use `kubernetes.client.CustomObjectsApi` with **group/version/plural from the live cluster**.
  - Prefer typed/generated models if your toolchain adds them; otherwise dict bodies with strict schema checks.
  - Keep CRD logic in a dedicated module; do not mix into `pod_spec` / `submitter` without SPEC update.

SPEC §5.3: explicit `Workload` CRD integration is **optional** and must match the cluster’s Kueue version and integration mode.

## Monitoring and errors

| Signal | Where |
|--------|--------|
| Queue name applied | `submissions.queue_name`, Job label, job index Redis record |
| Admission proxy | Job `spec.suspend` flip + `admitted` status via job watch |
| Execution | Job conditions, pod counts, `workload_error` on failure ([`workload_error.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/workload_error.py)) |
| Drift | [`drift_reconcile.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/drift_reconcile.py) — Job missing from cluster while DB still active |

There is **no** in-app subscriber to Kueue “inadmissible” events; use Kueue metrics/events or `kubectl describe` (see reference).

## Testing Kueue-related behavior

Without a live Kueue install, test **application obligations** only:

| Area | Tests / approach |
|------|------------------|
| Queue label on Jobs | [`test_labels.py`](../../../services/orchestrator/tests/test_labels.py) (`base_labels_for_job` + queue name) |
| Kind → queue resolution | Unit-test `Settings.kueue_local_queue_for_workload_kind` |
| Status mapping vs suspend | [`test_job_state.py`](../../../services/orchestrator/tests/test_job_state.py) |
| Submit path | Mock `BatchV1Api`; assert `suspend` and labels on `V1Job` body (extend submitter tests) |

End-to-end admission (LocalQueue backlog, preemption, flavor fit) belongs in **cluster integration** tests or manual checklists, not unit tests in this repo unless you add a gated env.

## Development rules

1. **Do not unsuspend Jobs** in orchestrator except if SPEC explicitly changes steady-state semantics.
2. **Do not expose LocalQueue choice in the public submit contract** without a product decision; keep routing in deployer config.
3. **Keep JobSet out of scope** unless SPEC and campaign contracts change.
4. **Match ClusterQueue capacity** to fixed request=limit pod templates when documenting sizing for users.
5. **Split concerns:** Kueue policy changes → ops/docs; label/suspend/resources → orchestrator + `kubernetes-development`.

## Additional reference

- Cluster operator checklist and kubectl flows: [reference.md](reference.md)
- Kueue labels (app uses queue-name): https://kueue.sigs.k8s.io/docs/reference/labels-and-annotations
