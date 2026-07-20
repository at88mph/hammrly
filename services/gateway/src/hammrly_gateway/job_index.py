from __future__ import annotations

import json
import logging
from typing import Any, Literal

import redis.asyncio as redis

from hammrly_gateway.config import Settings
from hammrly_gateway.redis_async import maybe_await

logger = logging.getLogger(__name__)

JobIndexStatus = Literal["pending", "received"]
INDEX_SCHEMA_VERSION = "1.0"


def index_key(settings: Settings, job_id: str) -> str:
    return f"{settings.job_index_redis_prefix}{job_id}"


def payload_summary_from_workload(workload: dict[str, Any]) -> dict[str, Any]:
    gpu = workload.get("gpu_count")
    if gpu is None:
        gpu = 0
    summary: dict[str, Any] = {
        "kind": workload.get("kind"),
        "name": workload.get("name"),
        "image": workload.get("image"),
        "gpu_count": int(gpu) if gpu is not None else 0,
        "needs_ingress": workload.get("needs_ingress"),
    }
    return summary


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


async def put_job_index(
    r: redis.Redis,
    settings: Settings,
    envelope: dict[str, Any],
    *,
    status: JobIndexStatus = "pending",
    queue_name: str | None = None,
) -> None:
    job_id = str(envelope["job_id"])
    record = build_index_record(envelope, status=status, queue_name=queue_name)
    payload = json.dumps(record, separators=(",", ":"), default=str)
    await maybe_await(
        r.set(
            index_key(settings, job_id),
            payload,
            ex=settings.job_index_ttl_seconds,
        )
    )


async def delete_job_index(r: redis.Redis, settings: Settings, job_id: str) -> None:
    await maybe_await(r.delete(index_key(settings, job_id)))
