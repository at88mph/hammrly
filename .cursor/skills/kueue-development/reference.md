# kueue-development reference

## Hammrly code map (Kueue touchpoints)

| Location | Kueue-related behavior |
|----------|-------------------------|
| `k8s/labels.py` | `KUEUE_LOCAL_QUEUE_LABEL`, `base_labels_for_job` |
| `k8s/submitter.py` | `suspend=True`, queue resolution, label on Job + template |
| `config.py` | `kueue_local_queue_*`, `kueue_local_queue_for_workload_kind` |
| `k8s/job_state.py` | `submitted_to_cluster` / `admitted` from Job `suspend` + counts |
| `cli.py`, `campaign/expander.py` | `queue_name` persisted at receive |
| `helm/orchestrator` | `session.kueue`, per-kind `queueName` env |
| `contracts/job-submission/v1/VALIDATION.md` | LocalQueue not in JSON; resource sizing for admission |

## Env / Helm quick reference

| Deployer input | Orchestrator env |
|----------------|------------------|
| `session.kueue.localQueueDefault` | `HAMMRLY_KUEUE_LOCAL_QUEUE_DEFAULT` |
| `session.kinds.<kind>.queueName` | `HAMMRLY_KUEUE_QUEUE_<KIND>` (uppercase kind) |

Workload namespace for Jobs: `HAMMRLY_K8S_NAMESPACE` / `k8sWorkloadNamespace` (see `helm/stack/README.md`).

## Kueue API (cluster; version-specific)

Typical API group: **`kueue.x-k8s.io`**. Common resources (names/plural stable; **apiVersion** depends on install):

| Kind | Role |
|------|------|
| `LocalQueue` | Namespace queue; label `kueue.x-k8s.io/queue-name` must reference an existing LocalQueue |
| `ClusterQueue` | Quota, flavors, preemption |
| `ResourceFlavor` | Node resources for quota |
| `Cohort` | Fair sharing between ClusterQueues |
| `Workload` | Admission unit; often linked from suspended `Job` when using built-in Job integration |

Confirm served versions:

```bash
kubectl api-resources | grep kueue
kubectl get localqueue,clusterqueue,workload -A
```

Use the [Kueue versioned docs](https://kueue.sigs.k8s.io/docs/) matching the controller image on **your** cluster.

## Troubleshooting pending and inadmissible workloads

Workflow (ops; adapt commands to your Kueue version docs):

1. **Job suspended long after submit** — `kubectl get job -n <workload-ns> <name> -o yaml` → `spec.suspend: true`, label `kueue.x-k8s.io/queue-name` present and matches a **LocalQueue** in that namespace.
2. **Kueue Workload** — find Workload owned by or associated with the Job (per your integration mode); `kubectl describe workload ...` for **admission**, **requeue**, **inadmissible** messages.
3. **ClusterQueue** — verify quotas for `cpu`, `memory`, `ephemeral-storage`, `nvidia.com/gpu` (and custom extended resources) against the Job’s **pod template** totals (init + sidecars + workload).
4. **ResourceFlavor** — GPU Jobs need flavors that match node labels; compare ClusterQueue flavor assignment with orchestrator `k8s_gpu_node_label_key` / `value`.
5. **Wrong queue** — compare `submissions.queue_name` / Job label with intended `HAMMRLY_KUEUE_*` config and Helm `session.kinds`.
6. **Orchestrator status** — `submitted_to_cluster` with suspend true is **expected** while waiting for Kueue; `admitted` means suspend cleared on the Job object (Kueue unsuspended) but pods may not be running yet.

Hammrly will **not** surface full Kueue admission reason strings in DB unless extended to read Workload status.

## Fair sharing, preemption, completion

- **Fair sharing / cohorts:** ClusterQueue and Cohort configuration only; Hammrly submits fixed-resource Jobs into a LocalQueue.
- **Preemption:** Kueue may preempt lower-priority Workloads per ClusterQueue policy; Hammrly observes resulting Job/Pod state via existing watches.
- **Completion:** Kueue releases quota when Workload finishes; Job TTL / platform GC ([`ttl_seconds_after_finished`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/submitter.py)) is separate from Kueue admission.

## Testing checklist (integration)

- [ ] LocalQueue exists for each `HAMMRLY_KUEUE_QUEUE_*` / default used in staging
- [ ] Suspended Job appears with correct labels before admission
- [ ] After admission, Job `spec.suspend` becomes `false` and DB reaches `admitted` → `running`
- [ ] Over-quota submit stays suspended; Kueue reports inadmissible (document expected UX)
- [ ] GPU headless/desktop requests fit a flavor with available `nvidia.com/gpu` quota
- [ ] Campaign N Jobs each admitted independently (no JobSet)

## Related skills and docs

- [`kubernetes-development`](../kubernetes-development/SKILL.md) — `V1Job`, resources, watches
- [Kueue concepts](https://kueue.sigs.k8s.io/docs/concepts/)
- [Integrating Jobs](https://kueue.sigs.k8s.io/docs/tasks/run/run_jobs/) (wording/version on site follows your install)
