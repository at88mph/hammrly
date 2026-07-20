from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import redis

from hammrly_query.config import Settings
from hammrly_query.contract_types import parse_payload_summary
from hammrly_query.jwt_auth import Principal

logger = logging.getLogger(__name__)


@dataclass
class JobIndexRecord:
    job_id: str
    submission_id: str
    tenant_id: str
    user_id: str
    status: str
    requested_at: str
    payload_summary: dict[str, Any]
    project_id: Optional[str] = None
    queue_name: Optional[str] = None


def index_key(settings: Settings, job_id: str) -> str:
    return f"{settings.job_index_redis_prefix}{job_id}"


def _parse_requested_at(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_job_index(r: redis.Redis, settings: Settings, job_id: str) -> Optional[JobIndexRecord]:
    raw = r.get(index_key(settings, job_id))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("corrupt job index payload for job_id=%s", job_id)
        return None
    try:
        ps = data.get("payload_summary") or {}
        if not isinstance(ps, dict):
            ps = {}
        return JobIndexRecord(
            job_id=str(data["job_id"]),
            submission_id=str(data["submission_id"]),
            tenant_id=str(data["tenant_id"]),
            user_id=str(data["user_id"]),
            status=str(data["status"]),
            requested_at=str(data["requested_at"]),
            payload_summary=ps,
            project_id=str(data["project_id"]) if data.get("project_id") else None,
            queue_name=str(data["queue_name"]) if data.get("queue_name") else None,
        )
    except (KeyError, TypeError):
        return None


def index_owned_by_principal(record: JobIndexRecord, principal: Principal, settings: Settings) -> bool:
    if record.user_id != principal.user_id:
        return False
    if principal.tenant_from_token and record.tenant_id != principal.tenant_from_token:
        return False
    return True


def index_to_detail(record: JobIndexRecord, settings: Settings) -> dict[str, Any]:
    requested = _parse_requested_at(record.requested_at)
    cluster_id = settings.cluster_id or "default"
    queue_name = record.queue_name or "default"
    ps = parse_payload_summary(record.payload_summary)
    gpu_count = ps.gpu_count if ps is not None and ps.gpu_count is not None else 0
    return {
        "job_id": UUID(record.job_id),
        "submission_id": UUID(record.submission_id),
        "tenant_id": record.tenant_id,
        "project_id": record.project_id,
        "user_id": record.user_id,
        "campaign_id": None,
        "item_key": None,
        "status": record.status,
        "status_detail": None,
        "queue_name": queue_name,
        "priority": None,
        "gpu_count": gpu_count,
        "cluster_id": cluster_id,
        "k8s_job_name": None,
        "k8s_namespace": None,
        "k8s_job_uid": None,
        "k8s_resource_version": None,
        "access_url": None,
        "requested_at": requested,
        "created_at": requested,
        "updated_at": requested,
        "payload_summary": ps,
        "events": [],
    }
