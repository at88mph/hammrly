from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from kubernetes.client import V1OwnerReference

from hammrly_orchestrator.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class SessionAccessDescriptor:
    """Public session URL and parts used for persistence (access_url column)."""

    public_url: Optional[str]
    host: Optional[str] = None
    path: Optional[str] = None
    scheme: Optional[str] = None


class EdgeBindingStrategy(Protocol):
    def apply(
        self,
        *,
        submitter: Any,
        namespace: str,
        ingress_name: str,
        service_name: str,
        host: str,
        path: str,
        submission_id: str,
        owner_refs: list[V1OwnerReference] | None = None,
    ) -> SessionAccessDescriptor:
        ...


class StandardKubernetesIngressStrategy:
    """Create networking.k8s.io/v1 Ingress; URL matches the rule."""

    def apply(
        self,
        *,
        submitter: Any,
        namespace: str,
        ingress_name: str,
        service_name: str,
        host: str,
        path: str,
        submission_id: str,
        owner_refs: list[V1OwnerReference] | None = None,
    ) -> SessionAccessDescriptor:
        if not host:
            return SessionAccessDescriptor(public_url=None, host=host or None, path=path)
        submitter._create_ingress(  # noqa: SLF001
            namespace,
            ingress_name,
            service_name,
            host,
            path,
            owner_refs=owner_refs,
        )
        scheme = submitter._settings.public_url_scheme  # noqa: SLF001
        public = _join_public_url(scheme, host, path)
        return SessionAccessDescriptor(
            public_url=public,
            host=host,
            path=path,
            scheme=scheme,
        )


class NoOpEdgeStrategy:
    """GitOps / no in-cluster Ingress: optionally still persist access_url from config + path templates."""

    def apply(
        self,
        *,
        submitter: Any,
        namespace: str,
        ingress_name: str,
        service_name: str,
        host: str,
        path: str,
        submission_id: str,
        owner_refs: list[V1OwnerReference] | None = None,
    ) -> SessionAccessDescriptor:
        scheme = submitter._settings.public_url_scheme  # noqa: SLF001
        if host:
            public = _join_public_url(scheme, host, path)
            return SessionAccessDescriptor(public_url=public, host=host, path=path, scheme=scheme)
        logger.info(
            "edge_binding=none: skipping Ingress for submission_id=%s (set HAMMRLY_K8S_INGRESS_HOST to persist access_url)",
            submission_id,
        )
        return SessionAccessDescriptor(public_url=None, host=None, path=path, scheme=scheme)


def _join_public_url(scheme: str, host: str, path: str) -> str:
    sch = (scheme or "https").rstrip(":").lower()
    p = path if path.startswith("/") else f"/{path}"
    if not p.endswith("/"):
        p = f"{p}/"
    return f"{sch}://{host}{p}"


def ingress_path_for_workload(settings: Settings, workload: dict[str, Any], submission_id: str) -> str:
    """Ingress path (leading slash, trailing slash) for this workload kind and submission."""
    kind = str(workload.get("kind", "") or "")
    templates: dict[str, Optional[str]] = {
        "desktop": settings.k8s_ingress_path_template_desktop,
        "notebook": settings.k8s_ingress_path_template_notebook,
        "carta": settings.k8s_ingress_path_template_carta,
        "contributed": settings.k8s_ingress_path_template_contributed,
        "headless": settings.k8s_ingress_path_template_headless,
    }
    tmpl = templates.get(kind)
    if tmpl:
        path = tmpl.format(submission_id=submission_id, kind=kind)
    else:
        prefix = settings.k8s_ingress_path_prefix.rstrip("/")
        path = f"{prefix}/sessions/{submission_id}"
    if not path.startswith("/"):
        path = f"/{path}"
    # if not path.endswith("/"):
    #     path = f"{path}/"
    return path


def edge_strategy_for_settings(settings: Settings) -> EdgeBindingStrategy:
    mode = (settings.k8s_edge_binding or "standard_ingress").strip().lower()
    if mode in ("none", "no_op", "gitops"):
        return NoOpEdgeStrategy()
    return StandardKubernetesIngressStrategy()
