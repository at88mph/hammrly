---
name: kubernetes-development
description: Guides Kubernetes integration work for the Hammrly orchestrator using the official kubernetes Python client (kubernetes>=28). Covers typed V1 models, BatchV1Api/CoreV1Api/NetworkingV1Api, Job/Pod/Service/Ingress construction, Kueue suspend+label integration, watches, and tests under services/orchestrator/src/hammrly_orchestrator/k8s/. Use when changing cluster submission, pod specs, labels, probes, edge binding, job/pod watch, drift reconcile, or Kueue queue mapping.
---

# Kubernetes development (Hammrly orchestrator)

Authoritative product behavior: [`services/orchestrator/SPEC.md`](../../../services/orchestrator/SPEC.md). Implementation lives in [`services/orchestrator/src/hammrly_orchestrator/k8s/`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/).

**Dependency:** `kubernetes>=28.0.0` ([kubernetes-client/python](https://github.com/kubernetes-client/python)) — match docs and model field names to this major line.

## Client model: synchronous only

This project uses the **synchronous** official client only. There is no `kubernetes_asyncio` usage.

| Concern | Pattern in repo |
|--------|------------------|
| Config | `kubernetes.config.load_incluster_config()` first; on `ConfigException`, `load_kube_config(config_file=settings.k8s_kubeconfig_path)` or default kubeconfig |
| API instances | `client.BatchV1Api()`, `client.CoreV1Api()`, `client.NetworkingV1Api()` after config load |
| Watches | `kubernetes.watch.Watch().stream(api.list_namespaced_* , ...)` on **daemon background threads** (`threading.Thread`), not asyncio |
| Lifecycle | `KubernetesSubmitter` loads config and APIs in `__init__`; watch/drift modules call a local `_configure_k8s(settings)` before creating API clients |

Do not introduce async K8s clients unless the orchestrator runtime model changes project-wide.

## Custom Resources (CRDs)

- Use `CustomObjectsApi` for interacting with Kubernetes custom resources
  when generated Python models are unavailable.
- Follow the CRD's API group, version, plural resource name, and schema.
- Do not assume custom resources follow the same conventions as
  built-in Kubernetes resources.
- Consult the installed CRD definition or authoritative documentation
  before constructing custom resource objects.
- Validate resource specifications against the CRD schema where practical.

### JobSet

- Treat JobSet as a Kubernetes custom resource.
- Follow the installed JobSet API version and specification.
- Understand its relationship to underlying Jobs, replicated Jobs,
  and Pods.
- Consult official JobSet documentation when implementing or
  modifying JobSet resources.

## API surface used today

| API class | Operations |
|-----------|------------|
| `BatchV1Api` | `create_namespaced_job`, `read_namespaced_job`, `list_namespaced_job` |
| `CoreV1Api` | `create_namespaced_service`, `list_namespaced_pod`, `read_namespaced_pod_log` |
| `NetworkingV1Api` | `create_namespaced_ingress` |

`CustomObjectsApi` is **not** used in the current tree. Prefer typed built-in APIs and `V1*` models for Jobs, Services, Ingress, Pods. Reserve `CustomObjectsApi` for future CRDs (e.g. explicit Kueue Workload objects) when generated typed models are unavailable—document group/version/plural and deserialize consistently with other call sites.

## Prefer typed models over unstructured dicts

Build and pass **`kubernetes.client` model instances** to API methods (`body=job`), not raw YAML/dict manifests.

**Entry points (extend these; avoid parallel builders):**

| Module | Responsibility |
|--------|----------------|
| [`submitter.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/submitter.py) | `KubernetesSubmitter.submit`: assembles `V1Job`, optional `V1Service` / `V1Ingress`, owner refs |
| [`pod_spec.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/pod_spec.py) | `build_pod_template` → `V1PodTemplateSpec` (containers, volumes, affinity, security) |
| [`probes.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/probes.py) | Envelope `kind_options.probes` (dict) → `V1Probe` / ports / env |
| [`labels.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/labels.py) | Label keys, Kueue queue label, RFC 1123 names from `submission_id` |
| [`edge_binding.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/edge_binding.py) | Ingress path templates + `EdgeBindingStrategy` |
| [`job_state.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/job_state.py) | Read `V1Job` status → DB status mapping (pure functions) |
| [`workload_error.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/workload_error.py) | Failure payloads from annotations / `CoreV1Api` logs |

Submission **envelopes** stay as `dict[str, Any]` at the Redis/CLI boundary; conversion to K8s types happens inside `k8s/`.

**Contract JSON → typed probes:** envelope fragments remain dicts where the API contract is JSON-shaped; [`probes.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/probes.py) translates them to `V1HTTPGetAction`, `V1Probe`, etc. Do not bypass that layer with hand-built probe dicts on `V1Container`.

## Resource construction checklist

### Jobs and Kueue

- Every submitted Job uses `V1JobSpec(suspend=True, template=..., ttl_seconds_after_finished=...)`.
- **Kueue integration (current):** label only — `kueue.x-k8s.io/queue-name` (`KUEUE_LOCAL_QUEUE_LABEL` in [`labels.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/labels.py)). Value from `Settings.kueue_local_queue_for_workload_kind(kind)`, not from the client envelope.
- Orchestrator **does not** patch `suspend` to `false` in steady state; Kueue admits and unsuspends Jobs per cluster config (see SPEC §5.3).
- Admission, LocalQueue/ClusterQueue policy, Job vs Workload lifecycle, and troubleshooting: use the [`kueue-development`](../kueue-development/SKILL.md) skill (not repeated here).
- Set `api_version` / `kind` on top-level objects where the submitter already does (`batch/v1` Job, `v1` Service, `networking.k8s.io/v1` Ingress).

### Pod template (workload pod)

- **Containers:** `workload` (main), init `input-downloader`, sidecar `output-watcher` (workspace I/O).
- **Volumes:** `emptyDir` workspace at `k8s_workspace_mount_path`; desktop kind adds in-memory `emptyDir` for `/dev/shm` (`k8s_desktop_shm_default`).
- **Resources:** [`resource_map_to_requirements`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/pod_spec.py) maps contract `workload.resources` to `V1ResourceRequirements` with **request and limit equal** for each key. Ephemeral storage goes through `apply_ephemeral_storage_policy` (GB strings, max from settings).
- **GPU:** `effective_gpu_count` / `nvidia.com/gpu`; node affinity via `k8s_gpu_node_label_key` / `value`; GPU tolerations when count > 0.
- **Security:** `workload_pod_security_context` and `workload_container_security_context` — non-root, drop ALL caps, `RuntimeDefault` seccomp; UID/GID from `k8s_job_run_as_user` / `k8s_job_run_as_group`.
- **Networking:** when `needs_service`, call `apply_workload_networking_to_container` (ports + probes + kind env).

### Service / Ingress / garbage collection

- Service selector uses **`hammrly.io/submission-id` only** (not full label set).
- Service and Ingress get `ownerReferences` to the created Job (`job_owner_references` in submitter) for GC when the Job is deleted.
- Ingress auth: `k8s_ingress_auth_annotations` on metadata when `k8s_ingress_auth_enabled`; edge mode from `k8s_edge_binding` (`standard_ingress` vs `none`/`gitops`).

### Namespaces and labels

- Create namespace: `settings.k8s_namespace`.
- Watch namespace/selectors: `job_watch_*`, `pod_watch_*` (typically same namespace, `hammrly.io/managed-by=orchestrator`).
- Standard labels: `hammrly.io/submission-id`, `job-id`, `tenant-id`, `user-id`, `workload-kind`, optional `campaign-id`; normalize long user/job ids via [`labels.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/labels.py).

## API operations and lifecycle

| Flow | Module |
|------|--------|
| Submit after envelope | `KubernetesSubmitter.submit` → persistence in CLI/campaign (outside `k8s/`) |
| Job watch → DB | [`job_watch.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/job_watch.py): initial `sync_jobs_once`, then watch; `DELETED` events; failed Jobs call `resolve_workload_error` |
| Session ready | [`pod_watch.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/pod_watch.py): Ready condition → `mark_session_ready` |
| Drift | [`drift_reconcile.py`](../../../services/orchestrator/src/hammrly_orchestrator/k8s/drift_reconcile.py): periodic LIST; missing Jobs → `mark_cluster_job_missing` |

Watch loops: handle `BOOKMARK` / `ERROR` events; on stream failure log, `sleep(3)`, new `Watch()`. Use `timeout_seconds` from settings.

## Exception handling

- **`ApiException`** on create: Job `409` → `read_namespaced_job` (idempotent submit); Service/Ingress `409` → log and return. Other statuses: log `status`, `reason`, `body` and re-raise (Jobs) or raise (Service/Ingress).
- **List/watch/read logs:** broad `Exception` in watch/drift/list paths → log with `logger.exception`, continue or backoff (do not crash the process).
- **Validation:** raise `ValueError` for envelope/spec mistakes before calling the API (e.g. `needs_ingress` without `needs_service`, invalid ephemeral storage).

Serialize API responses as returned model objects; persistence layers read fields from `V1Job` (see [`repository.py`](../../../services/orchestrator/src/hammrly_orchestrator/persistence/repository.py) for `resource_version`, uid, etc.).

## Testing

Tests live under [`services/orchestrator/tests/`](../../../services/orchestrator/tests/). Patterns:

1. **Pure builders** — call `build_pod_template`, `map_job_to_submission_status`, label helpers with typed fixtures (`V1Job`, `V1Container`, `SimpleNamespace` for partial status).
2. **Submitter / API boundary** — `@patch.object(KubernetesSubmitter, "_configure_client")`; replace `_batch`, `_core`, `_net` with `MagicMock`; assert `body` types (`V1Ingress`, etc.) in `side_effect` capture functions.
3. **No live cluster** required for unit tests; integration tests against a real API are out of scope unless explicitly added.

When adding behavior, add or extend tests beside existing `test_pod_spec_*`, `test_job_state*`, `test_submitter_*`, `test_probes`, `test_labels`, `test_workload_error`, `test_pod_watch`.

## Configuration reference

Kubernetes-related settings are on [`Settings`](../../../services/orchestrator/src/hammrly_orchestrator/config.py) (`HAMMRLY_K8S_*`, `HAMMRLY_KUEUE_*`, `HAMMRLY_JOB_WATCH_*`, `HAMMRLY_POD_WATCH_*`). See [`services/orchestrator/README.md`](../../../services/orchestrator/README.md) for env var names.

## Development rules

1. **Minimal diff** — change only `k8s/` and tightly coupled call sites; match naming and logging in neighboring code.
2. **No new abstractions** unless the existing module split cannot express the change (prefer extending `pod_spec`, `submitter`, `probes`, `labels`).
3. **No invented labels, annotations, or Kueue behavior** — align with SPEC and [Kueue labels](https://kueue.sigs.k8s.io/docs/reference/labels-and-annotations).
4. **Typed models first** — if you need a field on `V1Container`, set it on the model; avoid `client.ApiClient().sanitize_for_serialization` hacks unless the client requires it.
5. **Version-aware docs** — for client API details, use kubernetes-client/python docs for v28+; for Job suspend and networking API shapes, use Kubernetes API docs for the cluster version you deploy against.

## Module map

See [reference.md](reference.md) for a compact file index and external doc links.
