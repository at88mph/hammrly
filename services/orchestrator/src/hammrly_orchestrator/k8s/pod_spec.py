from __future__ import annotations

import copy
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from kubernetes.client import (
    V1Affinity,
    V1Capabilities,
    V1Container,
    V1EmptyDirVolumeSource,
    V1EnvVar,
    V1NodeAffinity,
    V1NodeSelector,
    V1NodeSelectorRequirement,
    V1NodeSelectorTerm,
    V1ObjectMeta,
    V1PodSpec,
    V1PodSecurityContext,
    V1PodTemplateSpec,
    V1ResourceRequirements,
    V1SeccompProfile,
    V1SecurityContext,
    V1Toleration,
    V1Volume,
    V1VolumeMount,
)

NVIDIA_GPU_RESOURCE_NAME = "nvidia.com/gpu"
EPHEMERAL_STORAGE_RESOURCE_NAME = "ephemeral_storage"
K8S_EPHEMERAL_STORAGE_RESOURCE_NAME = "ephemeral-storage"
WORKSPACE_VOLUME_NAME = "workspace"
DESKTOP_SHM_VOLUME_NAME = "dshm"
DEFAULT_DESKTOP_SHM_SIZE = "1Gi"
DEFAULT_WORKSPACE_MOUNT_PATH = "/workspace"
DEFAULT_WORKSPACE_TRANSFER_IMAGE = "python:3.12-alpine"
DEFAULT_COMPLETION_FILE = "hammrly-complete.json"
DEFAULT_ERROR_FILE = "hammrly-error.json"

_EPHEMERAL_STORAGE_GB_RE = re.compile(r"^([+]?(?:\d+(?:\.\d*)?|\.\d+))(?:G|GB)?$", re.IGNORECASE)

_INPUT_DOWNLOADER_SCRIPT = r"""
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

workspace = Path(os.environ.get("HAMMRLY_WORKSPACE", "/workspace"))
input_dir = Path(os.environ.get("HAMMRLY_INPUT_DIR", str(workspace / "inputs")))
output_dir = Path(os.environ.get("HAMMRLY_OUTPUT_DIR", str(workspace / "outputs")))
input_uri = os.environ.get("HAMMRLY_INPUT_URI", "").strip()

input_dir.mkdir(parents=True, exist_ok=True)
output_dir.mkdir(parents=True, exist_ok=True)

if not input_uri:
    print("No HAMMRLY_INPUT_URI set; initialized workspace only")
    sys.exit(0)

parts = urlsplit(input_uri)
name = Path(unquote(parts.path)).name or "input"
target = input_dir / name

if parts.scheme in ("http", "https"):
    with urlopen(input_uri) as response, target.open("wb") as out:
        shutil.copyfileobj(response, out)
elif parts.scheme == "file":
    source = Path(unquote(parts.path))
    if source.is_dir():
        target = input_dir / source.name
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)
elif not parts.scheme:
    source = Path(input_uri)
    if source.is_dir():
        target = input_dir / source.name
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)
else:
    raise SystemExit(f"Unsupported HAMMRLY_INPUT_URI scheme: {parts.scheme}")

print(f"Downloaded input to {target}")
""".strip()

_OUTPUT_WATCHER_SCRIPT = r"""
import json
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

workspace = Path(os.environ.get("HAMMRLY_WORKSPACE", "/workspace"))
completion_file = Path(os.environ.get("HAMMRLY_COMPLETION_FILE", str(workspace / "hammrly-complete.json")))
error_file = Path(os.environ.get("HAMMRLY_ERROR_FILE", str(workspace / "hammrly-error.json")))
default_output_uri = os.environ.get("HAMMRLY_OUTPUT_URI", "").strip()
poll_seconds = float(os.environ.get("HAMMRLY_WORKSPACE_POLL_SECONDS", "2"))


def read_json(path):
    last_error = None
    for _ in range(5):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            last_error = e
            time.sleep(0.5)
    raise SystemExit(f"Could not parse JSON file {path}: {last_error}")


def output_items(payload):
    raw = payload.get("outputs", []) if isinstance(payload, dict) else []
    if isinstance(raw, (str, dict)):
        raw = [raw]
    if not isinstance(raw, list):
        raise SystemExit("completion JSON field 'outputs' must be a list, object, or string")
    return raw


def join_destination(base, source_path):
    return base.rstrip("/") + "/" + Path(source_path).name


def normalize_item(item):
    if isinstance(item, str):
        return item, join_destination(default_output_uri, item) if default_output_uri else None
    if not isinstance(item, dict):
        raise SystemExit(f"Unsupported output entry: {item!r}")
    source = item.get("path") or item.get("source") or item.get("source_path")
    destination = item.get("destination_uri") or item.get("destination") or item.get("url") or item.get("uri")
    if not source:
        raise SystemExit(f"Output entry missing path/source: {item!r}")
    if not destination and default_output_uri:
        destination = join_destination(default_output_uri, str(source))
    return str(source), str(destination) if destination else None


def workspace_path(path_s):
    path = Path(path_s)
    return path if path.is_absolute() else workspace / path


def upload_file(source, destination):
    if not destination:
        raise SystemExit(f"No destination_uri for output {source}")
    parts = urlsplit(destination)
    if parts.scheme in ("http", "https"):
        request = Request(destination, data=source.read_bytes(), method="PUT")
        with urlopen(request) as response:
            print(f"Uploaded {source} to {destination}: HTTP {response.status}")
    elif parts.scheme == "file":
        target = Path(unquote(parts.path))
        if target.is_dir() or destination.endswith("/"):
            target = target / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Copied {source} to {target}")
    elif not parts.scheme:
        target = Path(destination)
        if target.is_dir() or destination.endswith("/"):
            target = target / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Copied {source} to {target}")
    else:
        raise SystemExit(f"Unsupported destination_uri scheme: {parts.scheme}")


print(f"Waiting for {completion_file} or {error_file}")
while True:
    if error_file.exists():
        payload = read_json(error_file)
        # Marker line for orchestrator log scrape + structured JSON for humans.
        print("HAMMRLY_WORKLOAD_ERROR=" + json.dumps(payload, sort_keys=True, separators=(",", ":")))
        print(json.dumps({"status": "error", "payload": payload}, sort_keys=True))
        sys.exit(1)
    if completion_file.exists():
        payload = read_json(completion_file)
        break
    time.sleep(poll_seconds)

count = 0
for item in output_items(payload):
    path_s, destination = normalize_item(item)
    source = workspace_path(path_s)
    if not source.is_file():
        raise SystemExit(f"Output path is not a file: {source}")
    upload_file(source, destination)
    count += 1

print(f"Processed completion file; uploaded {count} output(s)")
""".strip()


def _format_gb_quantity(gb: Decimal) -> str:
    s = format(gb.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return f"{s}G"


def _storage_gb_quantity(quantity: object) -> tuple[str, Decimal]:
    s = str(quantity).strip()
    if not s:
        raise ValueError("ephemeral storage GB value must be non-empty")
    m = _EPHEMERAL_STORAGE_GB_RE.fullmatch(s)
    if not m:
        raise ValueError(f"invalid ephemeral storage GB value: {s!r}")
    number_s = m.group(1)
    try:
        gb = Decimal(number_s)
    except InvalidOperation as e:
        raise ValueError(f"invalid ephemeral storage GB value: {s!r}") from e
    if gb <= 0:
        raise ValueError("ephemeral storage GB value must be greater than 0")
    return _format_gb_quantity(gb), gb


def apply_ephemeral_storage_policy(
    resources: dict[str, Any],
    *,
    default_request: str,
    maximum: str,
) -> dict[str, Any]:
    """Ensure every workload container has a bounded ephemeral-storage quantity."""
    default_canon, default_gb = _storage_gb_quantity(default_request)
    _max_canon, max_gb = _storage_gb_quantity(maximum)
    if default_gb > max_gb:
        raise ValueError("default ephemeral storage exceeds configured maximum")

    out = copy.deepcopy(resources)
    if EPHEMERAL_STORAGE_RESOURCE_NAME in out and K8S_EPHEMERAL_STORAGE_RESOURCE_NAME in out:
        raise ValueError("use only ephemeral_storage, not both ephemeral_storage and ephemeral-storage")
    if K8S_EPHEMERAL_STORAGE_RESOURCE_NAME in out:
        out[EPHEMERAL_STORAGE_RESOURCE_NAME] = out.pop(K8S_EPHEMERAL_STORAGE_RESOURCE_NAME)

    value = out.get(EPHEMERAL_STORAGE_RESOURCE_NAME)
    if value is None:
        out[EPHEMERAL_STORAGE_RESOURCE_NAME] = default_canon
        return out
    if isinstance(value, dict):
        raise ValueError(
            "workload.resources.ephemeral_storage must be a quantity string, not request/limit object"
        )

    canon, gb = _storage_gb_quantity(value)
    if gb > max_gb:
        raise ValueError("workload.resources.ephemeral_storage exceeds configured maximum")
    out[EPHEMERAL_STORAGE_RESOURCE_NAME] = canon
    return out


def resource_map_to_requirements(resources: dict[str, Any]) -> V1ResourceRequirements | None:
    """Map contract resource map to Kubernetes V1ResourceRequirements (request == limit)."""
    if not resources:
        return None
    requests: dict[str, str] = {}
    limits: dict[str, str] = {}

    for key, value in resources.items():
        if value is None:
            continue
        if isinstance(value, dict):
            raise ValueError(f"workload.resources.{key} must be a quantity string, not request/limit object")
        k8s_key = K8S_EPHEMERAL_STORAGE_RESOURCE_NAME if key == EPHEMERAL_STORAGE_RESOURCE_NAME else key
        quantity = str(value)
        requests[k8s_key] = quantity
        limits[k8s_key] = quantity

    if not requests:
        return None
    return V1ResourceRequirements(requests=requests, limits=limits)


def effective_gpu_count(workload: dict[str, Any]) -> int:
    """
    GPUs requested for scheduling: explicit workload.gpu_count, else legacy resources.nvidia.com/gpu.

    Whole numbers only (Kubernetes device plugin convention).
    """
    raw = workload.get("gpu_count")
    if raw is not None:
        try:
            if isinstance(raw, bool):
                return 0
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 0

    resources = workload.get("resources")
    if not isinstance(resources, dict):
        return 0
    gpu_value = resources.get(NVIDIA_GPU_RESOURCE_NAME)
    if gpu_value is None or isinstance(gpu_value, dict):
        return 0
    try:
        s = str(gpu_value).strip()
        if not s:
            return 0
        return max(0, int(s))
    except ValueError:
        return 0


def _resources_for_scheduling(workload: dict[str, Any], gpu_count: int) -> dict[str, Any]:
    """Deep-copy workload resources and align nvidia.com/gpu with effective GPU count."""
    base = workload.get("resources")
    out: dict[str, Any] = copy.deepcopy(base) if isinstance(base, dict) else {}
    if gpu_count > 0:
        out[NVIDIA_GPU_RESOURCE_NAME] = str(gpu_count)
    else:
        out.pop(NVIDIA_GPU_RESOURCE_NAME, None)
    return out


def _gpu_node_affinity(
    *, require_gpu_node: bool, label_key: str, label_value: str
) -> V1NodeAffinity:
    """Schedule only on GPU workers, or forbid GPU worker nodes."""
    op = "In" if require_gpu_node else "NotIn"
    return V1NodeAffinity(
        required_during_scheduling_ignored_during_execution=V1NodeSelector(
            node_selector_terms=[
                V1NodeSelectorTerm(
                    match_expressions=[
                        V1NodeSelectorRequirement(
                            key=label_key,
                            operator=op,
                            values=[label_value],
                        )
                    ]
                )
            ]
        )
    )


def _nvidia_gpu_tolerations() -> list[V1Toleration]:
    """Tolerate common NVIDIA device-plugin / GPU node taints."""
    return [
        V1Toleration(key=NVIDIA_GPU_RESOURCE_NAME, operator="Exists", effect="NoSchedule"),
    ]


def workload_pod_security_context(*, run_as_user: int, run_as_group: int) -> V1PodSecurityContext:
    return V1PodSecurityContext(
        run_as_non_root=True,
        run_as_user=run_as_user,
        run_as_group=run_as_group,
        fs_group=run_as_group,
        seccomp_profile=V1SeccompProfile(type="RuntimeDefault"),
    )


def workload_container_security_context(*, run_as_user: int, run_as_group: int) -> V1SecurityContext:
    return V1SecurityContext(
        allow_privilege_escalation=False,
        capabilities=V1Capabilities(drop=["ALL"]),
        privileged=False,
        run_as_non_root=True,
        run_as_user=run_as_user,
        run_as_group=run_as_group,
        seccomp_profile=V1SeccompProfile(type="RuntimeDefault"),
    )


def _workspace_child_path(workspace_mount_path: str, child: str) -> str:
    if child.startswith("/"):
        return child
    return f"{workspace_mount_path.rstrip('/')}/{child}"


def _workspace_env_vars(
    workload: dict[str, Any],
    *,
    workspace_mount_path: str,
    completion_file: str,
    error_file: str,
) -> list[V1EnvVar]:
    input_uri = str(workload.get("input_uri") or "").strip()
    output_uri = str(workload.get("output_uri") or "").strip()
    env = [
        V1EnvVar(name="HAMMRLY_WORKSPACE", value=workspace_mount_path),
        V1EnvVar(name="HAMMRLY_INPUT_DIR", value=_workspace_child_path(workspace_mount_path, "inputs")),
        V1EnvVar(name="HAMMRLY_OUTPUT_DIR", value=_workspace_child_path(workspace_mount_path, "outputs")),
        V1EnvVar(name="HAMMRLY_COMPLETION_FILE", value=_workspace_child_path(workspace_mount_path, completion_file)),
        V1EnvVar(name="HAMMRLY_ERROR_FILE", value=_workspace_child_path(workspace_mount_path, error_file)),
    ]
    if input_uri:
        env.append(V1EnvVar(name="HAMMRLY_INPUT_URI", value=input_uri))
    if output_uri:
        env.append(V1EnvVar(name="HAMMRLY_OUTPUT_URI", value=output_uri))
    return env


def _workspace_volume_mount(workspace_mount_path: str) -> V1VolumeMount:
    return V1VolumeMount(name=WORKSPACE_VOLUME_NAME, mount_path=workspace_mount_path)


def workspace_volume() -> V1Volume:
    return V1Volume(name=WORKSPACE_VOLUME_NAME, empty_dir=V1EmptyDirVolumeSource())


def desktop_shm_volume(*, size_limit: str = DEFAULT_DESKTOP_SHM_SIZE) -> V1Volume:
    """In-memory emptyDir for /dev/shm — avoids the tiny default container shm for GUI apps."""
    return V1Volume(
        name=DESKTOP_SHM_VOLUME_NAME,
        empty_dir=V1EmptyDirVolumeSource(medium="Memory", size_limit=size_limit),
    )


def _desktop_shm_volume_mount() -> V1VolumeMount:
    return V1VolumeMount(name=DESKTOP_SHM_VOLUME_NAME, mount_path="/dev/shm")


def input_downloader_container(
    workload: dict[str, Any],
    *,
    image: str,
    workspace_mount_path: str,
    completion_file: str,
    error_file: str,
    run_as_user: int,
    run_as_group: int,
) -> V1Container:
    return V1Container(
        name="input-downloader",
        image=image,
        command=["python", "-c", _INPUT_DOWNLOADER_SCRIPT],
        env=_workspace_env_vars(
            workload,
            workspace_mount_path=workspace_mount_path,
            completion_file=completion_file,
            error_file=error_file,
        ),
        volume_mounts=[_workspace_volume_mount(workspace_mount_path)],
        security_context=workload_container_security_context(
            run_as_user=run_as_user,
            run_as_group=run_as_group,
        ),
    )


def output_watcher_container(
    workload: dict[str, Any],
    *,
    image: str,
    workspace_mount_path: str,
    completion_file: str,
    error_file: str,
    run_as_user: int,
    run_as_group: int,
) -> V1Container:
    return V1Container(
        name="output-watcher",
        image=image,
        command=["python", "-c", _OUTPUT_WATCHER_SCRIPT],
        env=_workspace_env_vars(
            workload,
            workspace_mount_path=workspace_mount_path,
            completion_file=completion_file,
            error_file=error_file,
        ),
        volume_mounts=[_workspace_volume_mount(workspace_mount_path)],
        security_context=workload_container_security_context(
            run_as_user=run_as_user,
            run_as_group=run_as_group,
        ),
    )


def workload_container_port(workload: dict[str, Any]) -> int:
    """Default exposed port for Service/Ingress (interactive workloads)."""
    kind = workload.get("kind")
    ko: dict[str, Any] = workload.get("kind_options") or {}
    if kind == "desktop":
        return int((ko.get("novnc") or {}).get("port") or 6080)
    if kind == "notebook":
        return int((ko.get("jupyter") or {}).get("port") or 8888)
    if kind == "carta":
        return int((ko.get("carta") or {}).get("port") or 9090)
    if kind == "contributed":
        return 8080
    return 8080


def container_command_args(workload: dict[str, Any]) -> tuple[list[str] | None, list[str] | None]:
    kind = workload.get("kind")
    ko: dict[str, Any] = workload.get("kind_options") or {}
    if kind == "headless":
        b: dict[str, Any] = ko.get("batch") or {}
        cmd, args = b.get("command"), b.get("args")
        return (
            [str(x) for x in cmd] if isinstance(cmd, list) else None,
            [str(x) for x in args] if isinstance(args, list) else None,
        )
    if kind == "contributed":
        c: dict[str, Any] = ko.get("contributed") or {}
        cmd, args = c.get("command"), c.get("args")
        return (
            [str(x) for x in cmd] if isinstance(cmd, list) else None,
            [str(x) for x in args] if isinstance(args, list) else None,
        )
    return None, None


def build_pod_template(
    workload: dict[str, Any],
    labels: dict[str, str],
    *,
    gpu_node_label_key: str,
    gpu_node_label_value: str,
    default_ephemeral_storage: str = "20",
    max_ephemeral_storage: str = "20",
    job_run_as_user: int = 1000,
    job_run_as_group: int = 1000,
    workspace_mount_path: str = DEFAULT_WORKSPACE_MOUNT_PATH,
    workspace_transfer_image: str = DEFAULT_WORKSPACE_TRANSFER_IMAGE,
    workspace_completion_file: str = DEFAULT_COMPLETION_FILE,
    workspace_error_file: str = DEFAULT_ERROR_FILE,
    ingress_path: str = "",
    ingress_auth_disable_jupyter_token: bool = False,
    desktop_shm_size: str = DEFAULT_DESKTOP_SHM_SIZE,
) -> V1PodTemplateSpec:
    name = str(workload["name"])
    image = str(workload["image"])
    gpu_n = effective_gpu_count(workload)
    resources = _resources_for_scheduling(workload, gpu_n)
    resources = apply_ephemeral_storage_policy(
        resources,
        default_request=default_ephemeral_storage,
        maximum=max_ephemeral_storage,
    )
    res_req = resource_map_to_requirements(resources)

    cmd, args = container_command_args(workload)
    from hammrly_orchestrator.k8s.probes import apply_workload_networking_to_container

    container = V1Container(
        name="workload",
        image=image,
        command=cmd,
        args=args,
        resources=res_req,
        env=_workspace_env_vars(
            workload,
            workspace_mount_path=workspace_mount_path,
            completion_file=workspace_completion_file,
            error_file=workspace_error_file,
        ),
        volume_mounts=[_workspace_volume_mount(workspace_mount_path)],
        security_context=workload_container_security_context(
            run_as_user=job_run_as_user,
            run_as_group=job_run_as_group,
        ),
    )
    if workload.get("needs_service"):
        apply_workload_networking_to_container(
            container,
            workload,
            ingress_path=ingress_path,
            workload_port=workload_container_port(workload),
            disable_jupyter_token=ingress_auth_disable_jupyter_token,
        )
    volume_mounts = list(container.volume_mounts or [])
    if workload.get("kind") == "desktop":
        volume_mounts.append(_desktop_shm_volume_mount())
        container.volume_mounts = volume_mounts
    init_container = input_downloader_container(
        workload,
        image=workspace_transfer_image,
        workspace_mount_path=workspace_mount_path,
        completion_file=workspace_completion_file,
        error_file=workspace_error_file,
        run_as_user=job_run_as_user,
        run_as_group=job_run_as_group,
    )
    sidecar = output_watcher_container(
        workload,
        image=workspace_transfer_image,
        workspace_mount_path=workspace_mount_path,
        completion_file=workspace_completion_file,
        error_file=workspace_error_file,
        run_as_user=job_run_as_user,
        run_as_group=job_run_as_group,
    )

    annotations: dict[str, str] = {}
    extra_ann = workload.get("annotations")
    if isinstance(extra_ann, dict):
        for k, v in extra_ann.items():
            if isinstance(k, str) and isinstance(v, str):
                annotations[k] = v

    node_affinity = _gpu_node_affinity(
        require_gpu_node=gpu_n > 0,
        label_key=gpu_node_label_key,
        label_value=gpu_node_label_value,
    )
    affinity = V1Affinity(node_affinity=node_affinity)
    tolerations = _nvidia_gpu_tolerations() if gpu_n > 0 else None

    volumes = [workspace_volume()]
    if workload.get("kind") == "desktop":
        volumes.append(desktop_shm_volume(size_limit=desktop_shm_size))

    return V1PodTemplateSpec(
        metadata=V1ObjectMeta(labels=labels | {"hammrly.io/workload-name": name[:63]}, annotations=annotations or None),
        spec=V1PodSpec(
            restart_policy="Never",
            init_containers=[init_container],
            containers=[container, sidecar],
            volumes=volumes,
            affinity=affinity,
            tolerations=tolerations,
            security_context=workload_pod_security_context(
                run_as_user=job_run_as_user,
                run_as_group=job_run_as_group,
            ),
        ),
    )

