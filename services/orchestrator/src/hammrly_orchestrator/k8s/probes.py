"""Contract-defined workload probes and kind-specific runtime wiring for session pods.

Resolves ``kind_options.probes`` from the job-submission envelope (with platform
defaults for ``desktop``, ``notebook``, and ``carta``), expands ``{ingress_path}``
and ``"workload"`` port placeholders, and renders ``V1Probe`` objects plus
kind-specific env/args (e.g. Jupyter ``ServerApp.base_url``, NoVNC path prefix).
"""
from __future__ import annotations

from typing import Any, Optional

from kubernetes.client import (
    V1Container,
    V1ContainerPort,
    V1EnvVar,
    V1EnvVarSource,
    V1ExecAction,
    V1HTTPGetAction,
    V1Probe,
    V1SecretKeySelector,
    V1TCPSocketAction,
)

_INGRESS_PATH_PLACEHOLDER = "{ingress_path}"
_WORKLOAD_PORT_PLACEHOLDER = "{workload_port}"


def _probe_path_for_ingress(ingress_path: str) -> str:
    """Normalize ingress path for probe path prefix (leading slash, no trailing slash)."""
    p = (ingress_path or "").strip()
    if not p:
        return "/"
    if not p.startswith("/"):
        p = f"/{p}"
    return p.rstrip("/") or "/"


def resolve_probe_path(path: str, *, ingress_path: str) -> str:
    prefix = _probe_path_for_ingress(ingress_path)
    out = str(path).replace(_INGRESS_PATH_PLACEHOLDER, prefix)
    if _WORKLOAD_PORT_PLACEHOLDER in out:
        raise ValueError("workload_port placeholder is not valid in probe path")
    if not out.startswith("/"):
        out = f"/{out}"
    return out


def resolve_probe_port(port: Any, *, workload_port: int) -> int:
    if port is None:
        return workload_port
    if port == "workload":
        return workload_port
    return int(port)


def default_probes_for_kind(kind: str) -> dict[str, Any]:
    """Platform defaults when kind_options.probes is omitted (known interactive kinds)."""
    if kind == "notebook":
        return {
            "readiness": {
                "httpGet": {
                    "path": f"{_INGRESS_PATH_PLACEHOLDER}/api",
                    "port": "workload",
                },
                "initialDelaySeconds": 5,
                "periodSeconds": 10,
                "timeoutSeconds": 5,
                "failureThreshold": 12,
            },
        }
    if kind == "desktop":
        return {
            "readiness": {
                "httpGet": {
                    "path": f"{_INGRESS_PATH_PLACEHOLDER}/",
                    "port": "workload",
                },
                "initialDelaySeconds": 5,
                "periodSeconds": 10,
                "timeoutSeconds": 5,
                "failureThreshold": 12,
            },
            "startup": {
                "httpGet": {
                    "path": f"{_INGRESS_PATH_PLACEHOLDER}/",
                    "port": "workload",
                },
                "initialDelaySeconds": 10,
                "periodSeconds": 10,
                "timeoutSeconds": 5,
                "failureThreshold": 30,
            },
        }
    if kind == "carta":
        return {
            "readiness": {
                "httpGet": {
                    "path": "/",
                    "port": "workload",
                },
                "initialDelaySeconds": 5,
                "periodSeconds": 10,
                "timeoutSeconds": 5,
                "failureThreshold": 12,
            },
        }
    return {}


def resolve_workload_probes(workload: dict[str, Any]) -> dict[str, Any]:
    """Envelope probes merged with platform defaults for known kinds."""
    kind = str(workload.get("kind") or "")
    ko: dict[str, Any] = workload.get("kind_options") or {}
    explicit = ko.get("probes")
    if isinstance(explicit, dict) and explicit:
        return dict(explicit)
    return default_probes_for_kind(kind)


def _render_probe(
    spec: dict[str, Any],
    *,
    ingress_path: str,
    workload_port: int,
) -> V1Probe:
    http_get = spec.get("httpGet")
    tcp_socket = spec.get("tcpSocket")
    exec_spec = spec.get("exec")

    handler: Any = None
    if isinstance(http_get, dict):
        port = resolve_probe_port(http_get.get("port"), workload_port=workload_port)
        handler = V1HTTPGetAction(
            path=resolve_probe_path(str(http_get.get("path") or "/"), ingress_path=ingress_path),
            port=port,
            scheme=http_get.get("scheme") or "HTTP",
            host=http_get.get("host") or None,
        )
    elif isinstance(tcp_socket, dict):
        port = resolve_probe_port(tcp_socket.get("port"), workload_port=workload_port)
        handler = V1TCPSocketAction(
            port=port,
            host=tcp_socket.get("host") or None,
        )
    elif isinstance(exec_spec, dict):
        cmd = exec_spec.get("command")
        if not isinstance(cmd, list) or not cmd:
            raise ValueError("probe exec.command must be a non-empty array")
        handler = V1ExecAction(command=[str(x) for x in cmd])
    else:
        raise ValueError("probe must specify httpGet, tcpSocket, or exec")

    return V1Probe(
        _exec=handler if isinstance(handler, V1ExecAction) else None,
        http_get=handler if isinstance(handler, V1HTTPGetAction) else None,
        tcp_socket=handler if isinstance(handler, V1TCPSocketAction) else None,
        initial_delay_seconds=spec.get("initialDelaySeconds"),
        period_seconds=spec.get("periodSeconds"),
        timeout_seconds=spec.get("timeoutSeconds"),
        success_threshold=spec.get("successThreshold"),
        failure_threshold=spec.get("failureThreshold"),
    )


def render_container_probes(
    probes: dict[str, Any],
    *,
    ingress_path: str,
    workload_port: int,
) -> tuple[Optional[V1Probe], Optional[V1Probe], Optional[V1Probe]]:
    readiness = None
    liveness = None
    startup = None
    if isinstance(probes.get("readiness"), dict):
        readiness = _render_probe(probes["readiness"], ingress_path=ingress_path, workload_port=workload_port)
    if isinstance(probes.get("liveness"), dict):
        liveness = _render_probe(probes["liveness"], ingress_path=ingress_path, workload_port=workload_port)
    if isinstance(probes.get("startup"), dict):
        startup = _render_probe(probes["startup"], ingress_path=ingress_path, workload_port=workload_port)
    return readiness, liveness, startup


def kind_runtime_env_vars(
    workload: dict[str, Any],
    *,
    ingress_path: str,
    disable_jupyter_token: bool = False,
) -> list[V1EnvVar]:
    """Kind-specific env injection for ingress-backed interactive workloads."""
    kind = workload.get("kind")
    ko: dict[str, Any] = workload.get("kind_options") or {}
    env: list[V1EnvVar] = []
    prefix = _probe_path_for_ingress(ingress_path)
    base_url = f"{prefix}/" if prefix != "/" else "/"

    if kind == "notebook":
        # Jupyter docker-stack images read NOTEBOOK_ARGS; do not set container args (replaces image CMD).
        jupyter: dict[str, Any] = ko.get("jupyter") or {}
        notebook_args = f"--ServerApp.base_url={base_url}"
        if disable_jupyter_token:
            notebook_args = f"{notebook_args} --ServerApp.token=''"
        env.append(V1EnvVar(name="NOTEBOOK_ARGS", value=notebook_args))
        token_ref = jupyter.get("token_ref")
        if isinstance(token_ref, dict):
            secret_name = str(token_ref.get("secret_name") or "").strip()
            key = str(token_ref.get("key") or "").strip()
            if secret_name and key:
                env.append(
                    V1EnvVar(
                        name="JUPYTER_TOKEN",
                        value_from=V1EnvVarSource(
                            secret_key_ref=V1SecretKeySelector(name=secret_name, key=key),
                        ),
                    )
                )

    if kind == "desktop":
        novnc: dict[str, Any] = ko.get("novnc") or {}
        path_prefix = novnc.get("path_prefix")
        if path_prefix is None:
            path_prefix = base_url
        env.append(V1EnvVar(name="NOVNC_PATH_PREFIX", value=str(path_prefix)))

    return env


def apply_workload_networking_to_container(
    container: V1Container,
    workload: dict[str, Any],
    *,
    ingress_path: str,
    workload_port: int,
    disable_jupyter_token: bool = False,
) -> None:
    """Attach ports, probes, and kind env to the workload container."""
    container.ports = [
        V1ContainerPort(name="http", container_port=workload_port, protocol="TCP"),
    ]
    for env_var in kind_runtime_env_vars(
        workload,
        ingress_path=ingress_path,
        disable_jupyter_token=disable_jupyter_token,
    ):
        existing = list(container.env or [])
        existing.append(env_var)
        container.env = existing

    if workload.get("needs_service"):
        probes = resolve_workload_probes(workload)
        readiness, liveness, startup = render_container_probes(
            probes,
            ingress_path=ingress_path,
            workload_port=workload_port,
        )
        if readiness is not None:
            container.readiness_probe = readiness
        if liveness is not None:
            container.liveness_probe = liveness
        if startup is not None:
            container.startup_probe = startup
