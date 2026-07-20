from __future__ import annotations

import json
import logging
from typing import Any, Literal

import redis

from hammrly_orchestrator.config import Settings

logger = logging.getLogger(__name__)

JobIndexStatus = Literal["pending", "received"]
INDEX_SCHEMA_VERSION = "1.0"


def index_key(settings: Settings, job_id: str) -> str:
    return f"{settings.job_index_redis_prefix}{job_id}"


def payload_summary_from_workload(workload: dict[str, Any]) -> dict[str, Any]:
    gpu = workload.get("gpu_count")
    if gpu is None:
        gpu = 0
    return {
        "kind": workload.get("kind"),
        "name": workload.get("name"),
        "image": workload.get("image"),
        "gpu_count": int(gpu) if gpu is not None else 0,
        "needs_ingress": workload.get("needs_ingress"),
    }


def build_index_record(
    envelope: dict[str, Any],
    *,
    status: JobIndexStatus,
    queue_name: str | None = None,
) -> dict[str, Any]:
    workload = envelope.get("workload") or {}
    record: dict[str, Any] = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "job_id": str(envelope["job_id"]),
        "submission_id": str(envelope["submission_id"]),
        "tenant_id": str(envelope["tenant_id"]),
        "user_id": str(envelope["user_id"]),
        "status": status,
        "requested_at": str(envelope["requested_at"]),
        "payload_summary": payload_summary_from_workload(workload),
    }
    project_id = envelope.get("project_id")
    if project_id is not None and str(project_id).strip():
        record["project_id"] = str(project_id)
    if queue_name:
        record["queue_name"] = queue_name
    return record


def update_job_index_after_received(
    r: redis.Redis,
    settings: Settings,
    envelope: dict[str, Any],
    *,
    queue_name: str,
) -> None:
    job_id = envelope.get("job_id")
    if not job_id:
        return
    record = build_index_record(envelope, status="received", queue_name=queue_name)
    payload = json.dumps(record, separators=(",", ":"), default=str)
    r.set(index_key(settings, str(job_id)), payload, ex=settings.job_index_ttl_seconds)
