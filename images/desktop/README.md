# Hammrly desktop images

Reference OCI images for **`workload.kind=desktop`** interactive sessions. Clients pass the image reference in `POST /v2/session` (Hammrly does not resolve image names beyond schema validation).

Each variant is built from the directory named after its role. Images are layered:

```text
base  →  astronomy  →  gpu
```

## Variants

| Directory | Published name (example) | Purpose |
|-----------|--------------------------|---------|
| [`base/`](base/) | `desktop-base` | Minimal XFCE desktop with TigerVNC and noVNC. General interactive GUI work (browser, terminal, editors). |
| [`astronomy/`](astronomy/) | `desktop-astronomy` | Extends **base** with common astronomy tooling: Firefox, OpenJDK, TOPCAT, and Python packages (`astropy`, `numpy`, `matplotlib`). |
| [`gpu/`](gpu/) | `desktop-astronomy-gpu` | Extends **astronomy** with CUDA/OpenCL runtime libraries for GPU-accelerated pipelines. Submit with `workload.gpu_count > 0` so the orchestrator schedules on GPU worker nodes. |

## Hammrly runtime contract

Images in this tree are intended to satisfy the [desktop image runtime contract](../../contracts/job-submission/v1/VALIDATION.md#desktop-image-runtime-contract):

- Listen on **`kind_options.novnc.port`** (default **6080**; overridable via `NOVNC_PORT` in the container).
- Honor **`NOVNC_PATH_PREFIX`** (set by the orchestrator from the session ingress path).
- Run as non-root **UID/GID 1000** (matching `HAMMRLY_K8S_JOB_RUN_AS_USER` / `HAMMRLY_K8S_JOB_RUN_AS_GROUP`).
- Respond to the platform readiness probe at **`{ingress_path}/`** on the NoVNC port.

The orchestrator also mounts an in-memory **`/dev/shm`** volume on desktop pods (size from `HAMMRLY_K8S_DESKTOP_SHM_DEFAULT`, default `1Gi`); that is deployer configuration, not part of the image.

## Build

Build from the **repository root** so `COPY images/desktop/...` paths resolve:

```bash
docker build -f images/desktop/base/Dockerfile \
  -t hammrly/desktop-base:local .

docker build -f images/desktop/astronomy/Dockerfile \
  -t hammrly/desktop-astronomy:local .

docker build -f images/desktop/gpu/Dockerfile \
  -t hammrly/desktop-astronomy-gpu:local .
```

When publishing to a registry, pass the parent image tags:

```bash
docker build -f images/desktop/astronomy/Dockerfile \
  --build-arg BASE_IMAGE=registry.example/hammrly/desktop-base:1.0 \
  -t registry.example/hammrly/desktop-astronomy:1.0 .

docker build -f images/desktop/gpu/Dockerfile \
  --build-arg ASTRONOMY_IMAGE=registry.example/hammrly/desktop-astronomy:1.0 \
  -t registry.example/hammrly/desktop-astronomy-gpu:1.0 .
```

## Submit example

```bash
curl -sS -X POST http://localhost:8080/v2/session \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "my-project",
    "workload": {
      "kind": "desktop",
      "name": "my-desktop",
      "image": "registry.example/hammrly/desktop-astronomy:1.0",
      "resources": {
        "cpu": "4",
        "memory": "8Gi"
      },
      "kind_options": {
        "novnc": {"port": 6080}
      }
    }
  }'
```

For the GPU image, add `"gpu_count": 1` (or set `resources["nvidia.com/gpu"]`) and size CPU/memory for peak tool usage (browsers, CASA, TOPCAT, etc.).

## Notes

- **base** is intentionally small; add domain-specific packages in a derived Dockerfile rather than bloating the base layer.
- **astronomy** downloads TOPCAT at build time from [Star Bristol](https://www.star.bristol.ac.uk/mbt/topcat/topcat-full.jar); pin or mirror that artifact in production builds if you require reproducible digests.
- **gpu** installs the Ubuntu `nvidia-cuda-toolkit` metapackage for compute libraries. Cluster nodes still need the NVIDIA device plugin and a compatible host driver; the image does not install kernel drivers.
