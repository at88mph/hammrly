from __future__ import annotations

import json
import os
import socket
from typing import Any, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_consumer_name() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


class Settings(BaseSettings):
    """Environment-driven settings for the queue listener."""

    model_config = SettingsConfigDict(
        env_prefix="HAMMRLY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "k8s_kubeconfig_path",
        "k8s_ingress_host",
        "k8s_ingress_class_name",
        "kueue_queue_desktop",
        "kueue_queue_notebook",
        "kueue_queue_carta",
        "kueue_queue_contributed",
        "kueue_queue_headless",
        "k8s_ingress_path_template_desktop",
        "k8s_ingress_path_template_notebook",
        "k8s_ingress_path_template_carta",
        "k8s_ingress_path_template_contributed",
        "k8s_ingress_path_template_headless",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

    redis_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        description="Redis connection URL (env: HAMMRLY_REDIS_URL).",
    )
    redis_stream_key: str = Field(
        default="hammrly:job-submissions",
    )
    campaign_stream_key: str = Field(
        default="hammrly:campaign-submissions",
    )
    campaign_max_items: int = Field(default=100_000, ge=1, le=500_000)
    campaign_expand_chunk_size: int = Field(default=500, ge=1, le=5000)
    campaign_expand_rps: float = Field(
        default=10.0,
        ge=0.0,
        description="Max Kubernetes Job creates per second during campaign expansion; 0 = unlimited.",
    )
    redis_consumer_group: str = Field(
        default="orchestrator",
    )
    redis_consumer_name: str = Field(
        default_factory=_default_consumer_name,
    )
    redis_block_ms: int = Field(
        default=5_000,
        ge=1,
        description="BLOCK timeout for XREADGROUP (milliseconds).",
    )
    redis_read_count: int = Field(
        default=10,
        ge=1,
        description="COUNT hint for XREADGROUP batch size.",
    )
    job_index_redis_prefix: str = Field(default="hammrly:jobs:")
    job_index_ttl_seconds: int = Field(default=86_400, ge=60)
    accepted_schema_major: int = Field(
        default=1,
        ge=0,
        description="Reject envelopes whose schema_version major does not match.",
    )

    # --- Kubernetes (official kubernetes-client/python) ------------------------------
    k8s_submit_enabled: bool = Field(
        default=False,
        description="If true, apply suspended Job (+ optional Service/Ingress) after a valid envelope.",
    )
    k8s_namespace: str = Field(
        default="default",
        description="Namespace for Job, Service, and Ingress objects.",
    )
    k8s_kubeconfig_path: Optional[str] = Field(
        default=None,
        description="Path to kubeconfig file; empty uses in-cluster or default kube config discovery.",
    )
    kueue_local_queue_default: str = Field(
        default="default",
        description=(
            "Default Kueue LocalQueue for label kueue.x-k8s.io/queue-name when no per-kind override is set."
        ),
    )
    kueue_queue_desktop: Optional[str] = Field(
        default=None,
        description="LocalQueue name for workload.kind desktop (optional).",
    )
    kueue_queue_notebook: Optional[str] = Field(
        default=None,
        description="LocalQueue name for workload.kind notebook (optional).",
    )
    kueue_queue_carta: Optional[str] = Field(
        default=None,
        description="LocalQueue name for workload.kind carta (optional).",
    )
    kueue_queue_contributed: Optional[str] = Field(
        default=None,
        description="LocalQueue name for workload.kind contributed (optional).",
    )
    kueue_queue_headless: Optional[str] = Field(
        default=None,
        description="LocalQueue name for workload.kind headless (optional).",
    )
    k8s_service_type: str = Field(
        default="ClusterIP",
        description="Kubernetes Service type when workload.needs_service is true.",
    )
    k8s_ingress_host: Optional[str] = Field(
        default=None,
        description="HTTP Host for Ingress when workload.needs_ingress is true (required to create Ingress).",
    )
    k8s_ingress_path_prefix: str = Field(
        default="/hammrly",
        description="Path prefix before /sessions/{submission_id}/ when no per-kind template is set.",
    )
    k8s_ingress_path_template_desktop: Optional[str] = Field(
        default=None,
        description="Optional .format template with {submission_id} and {kind} for desktop Ingress path.",
    )
    k8s_ingress_path_template_notebook: Optional[str] = Field(default=None)
    k8s_ingress_path_template_carta: Optional[str] = Field(default=None)
    k8s_ingress_path_template_contributed: Optional[str] = Field(default=None)
    k8s_ingress_path_template_headless: Optional[str] = Field(default=None)
    k8s_edge_binding: str = Field(
        default="standard_ingress",
        description=(
            "Edge behavior: standard_ingress creates networking.k8s.io/v1 Ingress; "
            "none skips Ingress creation (GitOps) but may still persist access_url when host is set."
        ),
    )
    public_url_scheme: str = Field(
        default="https",
        description="URL scheme for persisted access_url (e.g. https or http for dev).",
    )
    k8s_ingress_class_name: Optional[str] = Field(
        default=None,
        description="IngressClass name (spec.ingressClassName) when creating Ingress.",
    )
    k8s_ingress_auth_enabled: bool = Field(
        default=False,
        description="If true, apply k8s_ingress_auth_annotations to session Ingress resources.",
    )
    k8s_ingress_auth_annotations: dict[str, str] = Field(
        default_factory=dict,
        description="JSON object of Ingress metadata.annotations for session edge auth (vendor-neutral).",
    )
    k8s_ingress_auth_disable_jupyter_token: bool = Field(
        default=True,
        description="When ingress auth is enabled, disable Jupyter ServerApp.token on notebook workloads.",
    )
    k8s_gpu_node_label_key: str = Field(
        default="skaha.opencadc.org/node-type",
        description=(
            "Node label key used to select GPU worker nodes when workload.gpu_count > 0 "
            "and to exclude them when gpu_count is 0."
        ),
    )
    k8s_gpu_node_label_value: str = Field(
        default="gpu-worker-node",
        description="Node label value matching GPU worker nodes (used with k8s_gpu_node_label_key).",
    )
    k8s_ephemeral_storage_default: str = Field(
        default="20",
        description="Default workload ephemeral-storage request in GB when the envelope omits it.",
    )
    k8s_ephemeral_storage_max: str = Field(
        default="20",
        description="Maximum workload ephemeral-storage quantity in GB allowed for created Jobs.",
    )
    k8s_job_run_as_user: int = Field(
        default=1000,
        ge=1,
        description="Non-root UID used for workload Job containers.",
    )
    k8s_job_run_as_group: int = Field(
        default=1000,
        ge=1,
        description="Non-root GID/fsGroup used for workload Job pods and containers.",
    )
    k8s_workspace_mount_path: str = Field(
        default="/workspace",
        description="Mount path for the per-Job emptyDir workspace shared by init, workload, and sidecar containers.",
    )
    k8s_workspace_transfer_image: str = Field(
        default="python:3.12-alpine",
        description="Image used by workspace init/sidecar helper containers for input download and output upload.",
    )
    k8s_workspace_completion_file: str = Field(
        default="hammrly-complete.json",
        description="Workspace-relative JSON file that marks successful workload completion.",
    )
    k8s_workspace_error_file: str = Field(
        default="hammrly-error.json",
        description="Workspace-relative JSON file that marks workload failure.",
    )
    k8s_desktop_shm_default: str = Field(
        default="1Gi",
        description=(
            "Size of the in-memory emptyDir mounted at /dev/shm for desktop workloads "
            "(Kubernetes quantity, e.g. 1Gi). Deployer-only; not part of the submission envelope."
        ),
    )

    # --- PostgreSQL (required) ---------------------------------------------------
    database_url: str = Field(
        description="SQLAlchemy URL, e.g. postgresql+psycopg2://user:pass@host:5432/dbname",
        min_length=1,
    )
    cluster_id: str = Field(
        default="default",
        description="Logical cluster id stored on submissions rows.",
    )

    # --- Job watch + drift -------------------------------------------------------
    job_watch_enabled: bool = Field(
        default=False,
        description="If true, background Job watch reconciles status into persistence.",
    )
    job_watch_namespace: str = Field(
        default="default",
        description="Namespace for list/watch Jobs (usually same as k8s_namespace).",
    )
    job_watch_label_selector: str = Field(
        default="hammrly.io/managed-by=orchestrator",
        description="Label selector scoping watched Jobs.",
    )
    job_watch_timeout_seconds: int = Field(
        default=300,
        ge=30,
        description="kubernetes watch.stream timeout_seconds (reconnect after).",
    )
    job_drift_reconcile_interval_sec: int = Field(
        default=300,
        ge=0,
        description="Periodic LIST reconcile interval; 0 disables drift loop.",
    )

    pod_watch_enabled: bool = Field(
        default=False,
        description="If true, background Pod watch marks ingress-backed sessions ready when pods become Ready.",
    )
    pod_watch_namespace: str = Field(
        default="default",
        description="Namespace for list/watch Pods (usually same as k8s_namespace).",
    )
    pod_watch_label_selector: str = Field(
        default="hammrly.io/managed-by=orchestrator",
        description="Label selector scoping watched Pods.",
    )
    pod_watch_timeout_seconds: int = Field(
        default=300,
        ge=30,
        description="kubernetes watch.stream timeout_seconds for pod watch (reconnect after).",
    )

    @field_validator("k8s_ingress_auth_annotations", mode="before")
    @classmethod
    def _parse_ingress_auth_annotations(cls, v: Any) -> dict[str, str]:
        if v is None or v == "":
            return {}
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items()}
        if isinstance(v, str):
            parsed = json.loads(v)
            if not isinstance(parsed, dict):
                raise ValueError("k8s_ingress_auth_annotations must be a JSON object")
            return {str(k): str(val) for k, val in parsed.items()}
        raise ValueError("k8s_ingress_auth_annotations must be a JSON object or dict")

    @field_validator("k8s_ingress_path_prefix", mode="after")
    @classmethod
    def _normalize_ingress_path_prefix(cls, v: str) -> str:
        p = (v or "").strip()
        if not p:
            return "/hammrly"
        return p if p.startswith("/") else f"/{p}"

    @field_validator("public_url_scheme", mode="after")
    @classmethod
    def _normalize_public_url_scheme(cls, v: str) -> str:
        s = str(v).strip().rstrip(":").lower()
        return s if s else "https"

    @field_validator("k8s_ephemeral_storage_default", "k8s_ephemeral_storage_max", mode="after")
    @classmethod
    def _normalize_ephemeral_storage_quantity(cls, v: str) -> str:
        s = str(v).strip()
        return s if s else "20"

    @field_validator("k8s_workspace_mount_path", mode="after")
    @classmethod
    def _normalize_workspace_mount_path(cls, v: str | None) -> str:
        p = str(v or "").strip() or "/workspace"
        return p if p.startswith("/") else f"/{p}"

    @field_validator(
        "k8s_workspace_transfer_image",
        "k8s_workspace_completion_file",
        "k8s_workspace_error_file",
        mode="after",
    )
    @classmethod
    def _normalize_non_empty_workspace_setting(cls, v: str | None) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError("workspace settings must be non-empty")
        return s

    @field_validator("k8s_edge_binding", mode="after")
    @classmethod
    def _normalize_k8s_edge_binding(cls, v: str) -> str:
        return str(v).strip().lower() or "standard_ingress"

    def kueue_local_queue_for_workload_kind(self, kind: str) -> str:
        """Resolve Kueue LocalQueue name from workload.kind and orchestrator config."""
        by_kind: dict[str, Optional[str]] = {
            "desktop": self.kueue_queue_desktop,
            "notebook": self.kueue_queue_notebook,
            "carta": self.kueue_queue_carta,
            "contributed": self.kueue_queue_contributed,
            "headless": self.kueue_queue_headless,
        }
        specific = by_kind.get(kind)
        if specific is not None and str(specific).strip():
            return str(specific).strip()
        d = self.kueue_local_queue_default.strip()
        return d if d else "default"
