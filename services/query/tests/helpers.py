from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import jwt


def hs256_token(
    *,
    sub: str = "user-1",
    tenant: str = "tenant-z",
    scope: str | None = "hammrly:jobs:read",
    secret: str = "query-unit-test-hmac-secret-at-least-32b",
) -> str:
    claims: dict[str, Any] = {"sub": sub, "hammrly_tenant_id": tenant}
    if scope is not None:
        claims["scope"] = scope
    return jwt.encode(claims, secret, algorithm="HS256")


def sample_submission_row() -> SimpleNamespace:
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        job_id="550e8400-e29b-41d4-a716-446655440000",
        submission_id="660e8400-e29b-41d4-a716-446655440001",
        tenant_id="tenant-z",
        project_id=None,
        user_id="user-1",
        status="running",
        status_detail=None,
        queue_name="default",
        priority=1,
        gpu_count=0,
        cluster_id="default",
        k8s_job_name="job-1",
        k8s_namespace="ns",
        k8s_job_uid="uid-1",
        k8s_resource_version="rv-1",
        access_url="https://sessions.example/hammrly/sessions/x/",
        requested_at=now,
        created_at=now,
        updated_at=now,
        payload_summary={"kind": "desktop", "name": "n", "image": "img", "gpu_count": 0},
    )


def sample_event() -> SimpleNamespace:
    now = datetime(2026, 1, 15, 12, 1, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=1,
        event_type="queued",
        payload_json=None,
        occurred_at=now,
    )
