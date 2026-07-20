from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from hammrly_gateway.config import Settings
from hammrly_gateway.jwt_auth import Principal


def canonical_body_hash(parts: dict[str, Any]) -> str:
    """Stable hash for idempotency comparison (tenant, project, workload, correlation)."""
    blob = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def resolve_tenant_id(
    body_tenant: Optional[str],
    principal: Principal,
    settings: Settings,
) -> str:
    token_t = principal.tenant_from_token
    body_t = (body_tenant or "").strip() or None

    if token_t and body_t:
        if settings.tenant_mismatch_forbidden and token_t != body_t:
            raise PermissionError("tenant_mismatch: JWT tenant does not match body tenant_id")
        return token_t
    if token_t:
        return token_t
    if body_t:
        if not settings.tenant_body_allowed:
            raise PermissionError("tenant_required_in_token")
        return body_t
    raise ValueError("tenant_id is required (JWT claim or request body)")


def job_status_url(settings: Settings, job_id: str) -> str:
    """Query API URL (or path) for polling session lifecycle after POST /v2/session."""
    path = settings.query_job_status_path_template.format(job_id=job_id)
    if not path.startswith("/"):
        path = f"/{path}"
    base = settings.query_public_base_url
    if base:
        return f"{base}{path}"
    return path


def build_envelope(
    *,
    settings: Settings,
    principal: Principal,
    tenant_id: str,
    project_id: Optional[str],
    workload: dict[str, Any],
    correlation: Optional[dict[str, Any]],
    submission_id: UUID,
    job_id: UUID,
) -> dict[str, Any]:
    env: dict[str, Any] = {
        "schema_version": settings.submission_schema_version,
        "submission_id": str(submission_id),
        "job_id": str(job_id),
        "tenant_id": tenant_id,
        "user_id": principal.user_id,
        "requested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "workload": workload,
    }
    if project_id is not None:
        p = str(project_id).strip()
        if p:
            env["project_id"] = p
    if correlation:
        corr: dict[str, Any] = {}
        for k in ("trace_id", "span_id", "client_request_id"):
            if k in correlation and correlation[k] is not None:
                corr[k] = str(correlation[k])
        if corr:
            env["correlation"] = corr
    return env


def new_job_id() -> UUID:
    return uuid4()
