# Hammrly orchestrator

Minimal Python worker: consumes [job submission envelopes](../../contracts/job-submission/v1/schema.json) from a **Redis Stream** using consumer groups.

Requires **Python 3.9+** (3.11+ recommended).

## Run locally

```bash
cd services/orchestrator
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

export HAMMRLY_DATABASE_URL='postgresql+psycopg2://user:pass@localhost:5432/hammrly'
hammrly-orchestrator
```

`HAMMRLY_DATABASE_URL` is **required**. Or: `python -m hammrly_orchestrator`

## Configuration

Environment variables (prefix `HAMMRLY_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `HAMMRLY_REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis connection URL |
| `HAMMRLY_REDIS_STREAM_KEY` | `hammrly:job-submissions` | Stream key for `XADD` / `XREADGROUP` |
| `HAMMRLY_REDIS_CONSUMER_GROUP` | `orchestrator` | Consumer group name |
| `HAMMRLY_REDIS_CONSUMER_NAME` | `hostname-pid` | Unique consumer within the group |
| `HAMMRLY_REDIS_BLOCK_MS` | `5000` | `XREADGROUP` block timeout (ms) |
| `HAMMRLY_REDIS_READ_COUNT` | `10` | `COUNT` batch hint |

The orchestrator sets the Redis client `socket_timeout` to **block_ms + 5 seconds** so `XREADGROUP` blocking reads do not hit redis-py’s default 5s socket timeout (which would raise `TimeoutError` while the server is still waiting). The gateway only issues short commands (`PING`, `XADD`) and is unaffected.
| `HAMMRLY_ACCEPTED_SCHEMA_MAJOR` | `1` | Reject envelopes with a different `schema_version` major |
| `HAMMRLY_K8S_SUBMIT_ENABLED` | `false` | Set `true` to create suspended Jobs (and optional Service/Ingress) in the cluster |
| `HAMMRLY_K8S_NAMESPACE` | `default` | Target namespace for Job / Service / Ingress |
| `HAMMRLY_K8S_KUBECONFIG_PATH` | _(unset)_ | Kubeconfig path; in-cluster or default kubeconfig when unset |
| `HAMMRLY_KUEUE_LOCAL_QUEUE_DEFAULT` | `default` | Default **Kueue `LocalQueue`** for label `kueue.x-k8s.io/queue-name` when no per-`kind` override is set |
| `HAMMRLY_KUEUE_QUEUE_DESKTOP` | _(unset)_ | Override LocalQueue for `workload.kind=desktop` |
| `HAMMRLY_KUEUE_QUEUE_NOTEBOOK` | _(unset)_ | Override for `notebook` |
| `HAMMRLY_KUEUE_QUEUE_CARTA` | _(unset)_ | Override for `carta` |
| `HAMMRLY_KUEUE_QUEUE_CONTRIBUTED` | _(unset)_ | Override for `contributed` |
| `HAMMRLY_KUEUE_QUEUE_HEADLESS` | _(unset)_ | Override for `headless` |
| `HAMMRLY_K8S_SERVICE_TYPE` | `ClusterIP` | Kubernetes Service `spec.type` when `needs_service` is true |
| `HAMMRLY_K8S_INGRESS_HOST` | _(unset)_ | Ingress `spec.rules[].host` when `needs_ingress` is true (Ingress skipped if unset) |
| `HAMMRLY_K8S_INGRESS_PATH_PREFIX` | `/hammrly` | Path prefix; rule path is `{prefix}/sessions/{submission_id}/` |
| `HAMMRLY_K8S_INGRESS_CLASS_NAME` | _(unset)_ | `spec.ingressClassName` on Ingress |
| `HAMMRLY_K8S_INGRESS_AUTH_ENABLED` | `false` | Apply `HAMMRLY_K8S_INGRESS_AUTH_ANNOTATIONS` to session Ingress metadata |
| `HAMMRLY_K8S_INGRESS_AUTH_ANNOTATIONS` | `{}` | JSON object of Ingress annotations (vendor-neutral; set by Helm from `ingress.auth.profile`) |
| `HAMMRLY_K8S_INGRESS_AUTH_DISABLE_JUPYTER_TOKEN` | `true` | When ingress auth is on, set `--ServerApp.token=''` on notebook workloads |
| `HAMMRLY_K8S_GPU_NODE_LABEL_KEY` | `skaha.opencadc.org/node-type` | Node label key for GPU workers (`workload.gpu_count` scheduling). |
| `HAMMRLY_K8S_GPU_NODE_LABEL_VALUE` | `gpu-worker-node` | Label value for GPU worker nodes (must match cluster nodes). |
| `HAMMRLY_K8S_EPHEMERAL_STORAGE_DEFAULT` | `20` | Default workload container `ephemeral-storage` request in GB. |
| `HAMMRLY_K8S_EPHEMERAL_STORAGE_MAX` | `20` | Maximum workload container `ephemeral-storage` quantity in GB allowed by this cluster deployer. |
| `HAMMRLY_K8S_JOB_RUN_AS_USER` | `1000` | Non-root UID used for workload Job containers. |
| `HAMMRLY_K8S_JOB_RUN_AS_GROUP` | `1000` | Non-root GID/fsGroup used for workload Job pods and containers. |
| `HAMMRLY_K8S_WORKSPACE_MOUNT_PATH` | `/workspace` | Per-Job `emptyDir` mount path shared by init, workload, and sidecar containers. |
| `HAMMRLY_K8S_WORKSPACE_TRANSFER_IMAGE` | `python:3.12-alpine` | Helper image used for workspace input download and output upload containers. |
| `HAMMRLY_K8S_WORKSPACE_COMPLETION_FILE` | `hammrly-complete.json` | Workspace-relative JSON file that marks successful workload completion. |
| `HAMMRLY_K8S_WORKSPACE_ERROR_FILE` | `hammrly-error.json` | Workspace-relative JSON file that marks workload failure. |
| `HAMMRLY_K8S_DESKTOP_SHM_DEFAULT` | `1Gi` | In-memory `emptyDir` size mounted at `/dev/shm` for `workload.kind=desktop` (deployer-only; not in submit JSON). |

Optional: `.env` in the working directory is loaded automatically.

**Desktop sessions:** submit with `workload.kind=desktop` and caller-chosen `workload.image`. The orchestrator sets `NOVNC_PATH_PREFIX`, ingress-aligned readiness/startup probes, and the `/dev/shm` mount described above. See [VALIDATION.md](../../contracts/job-submission/v1/VALIDATION.md) for resource guidance and image runtime contract.

**GPU scheduling:** when `workload.gpu_count` is **0** (or omitted and no `nvidia.com/gpu` in `resources`), the pod spec uses **required** node affinity **`NotIn`** for that label so Jobs are not placed on GPU nodes. When `gpu_count` **> 0**, the orchestrator sets `nvidia.com/gpu` requests/limits, **`In`** affinity for GPU nodes, and a standard **`nvidia.com/gpu` Exists / NoSchedule** toleration.

**Workspace data flow:** each workload Job has an `input-downloader` init container, the main `workload` container, and an `output-watcher` sidecar sharing an `emptyDir` mounted at `/workspace`. The init container downloads optional `workload.input_uri` into `/workspace/inputs`; the workload writes outputs to `/workspace/outputs` and finishes by writing `/workspace/hammrly-complete.json` or `/workspace/hammrly-error.json` using the [workload completion contract](../../contracts/workload-completion/v1/schema.json); the sidecar uploads completion `outputs` entries and exits nonzero for error JSON.

### PostgreSQL and job watch

PostgreSQL is **required**: the orchestrator writes submission lifecycle rows to `submissions` / `submission_events` and (when enabled) reconciles Kubernetes Job status via a label-scoped watch plus periodic LIST drift checks. The orchestrator remains the only writer of automated lifecycle fields; a separate **query service** should use read-only access (replica DSN or `SELECT`-only DB user). See [SPEC §6](SPEC.md).

| Variable | Default | Description |
|----------|---------|-------------|
| `HAMMRLY_DATABASE_URL` | _(required)_ | SQLAlchemy URL, e.g. `postgresql+psycopg2://user:pass@host:5432/dbname` |
| `HAMMRLY_CLUSTER_ID` | `default` | Logical cluster id stored on submissions rows |
| `HAMMRLY_CAMPAIGN_STREAM_KEY` | `hammrly:campaign-submissions` | Redis stream for headless campaign expansion |
| `HAMMRLY_CAMPAIGN_MAX_ITEMS` | `100000` | Max items per campaign after manifest expand |
| `HAMMRLY_CAMPAIGN_EXPAND_CHUNK_SIZE` | `500` | Items processed per expansion batch |
| `HAMMRLY_CAMPAIGN_EXPAND_RPS` | `10` | Max K8s Job creates/sec during expansion (`0` = unlimited) |
| `HAMMRLY_JOB_WATCH_ENABLED` | `false` | When `true`, run a `batch/v1` Job watch in a background thread |
| `HAMMRLY_JOB_WATCH_NAMESPACE` | _(same as `HAMMRLY_K8S_NAMESPACE`)_ | Namespace for the watch `list_namespaced_job` call |
| `HAMMRLY_JOB_LABEL_SELECTOR` | (see config) | Label selector for managed Jobs; default includes `hammrly.io/managed-by=orchestrator` |
| `HAMMRLY_JOB_DRIFT_RECONCILE_INTERVAL_SEC` | `300` | Interval for LIST-based reconcile of DB “active” rows against the cluster; `0` disables |
| `HAMMRLY_POD_WATCH_ENABLED` | `false` | When `true`, watch Pods and set `status=ready` + `session_ready` after readiness probes pass (ingress-backed workloads) |
| `HAMMRLY_POD_WATCH_NAMESPACE` | _(same as job watch namespace)_ | Namespace for pod list/watch |
| `HAMMRLY_POD_WATCH_LABEL_SELECTOR` | `hammrly.io/managed-by=orchestrator` | Label selector for session pods |

**HA:** multiple orchestrator replicas may all run the same watch; updates are idempotent on `submission_id` and `k8s_resource_version`. For very large clusters, consider a single active watcher via Kubernetes **Lease** leader election (optional future work).

#### Database migrations (Alembic)

From `services/orchestrator`:

```bash
export HAMMRLY_DATABASE_URL='postgresql+psycopg2://user:pass@localhost:5432/hammrly'
PYTHONPATH=src alembic upgrade head
```

From the **repository root**, using the orchestrator image (no bind mount required; `alembic` is on `PATH` at `/usr/local/bin/alembic`):

```bash
docker run --rm -w /app \
  -e HAMMRLY_DATABASE_URL='postgresql+psycopg2://user:pass@host:5432/hammrly' \
  hammrly/orchestrator:0.2.0 \
  alembic upgrade head
```

Kubernetes API access uses the official **`kubernetes`** Python library ([kubernetes-client/python](https://github.com/kubernetes-client/python)).

## Wire format

Each stream entry must include a **`payload`** field whose value is UTF-8 JSON of the envelope (`XADD stream * payload '<json>'`).
