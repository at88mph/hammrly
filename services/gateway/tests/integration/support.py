"""Helpers for live-stack integration tests."""
from __future__ import annotations

import os
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class IntegrationSettings:
    gateway_url: str
    query_url: str
    jwt_secret: str
    tenant_id: str
    project_id: str
    notebook_image: str
    desktop_image: str | None
    poll_timeout_sec: float
    tls_verify: bool


def integration_settings_from_env() -> IntegrationSettings:
    insecure = os.environ.get("HAMMRLY_INTEGRATION_INSECURE_TLS", "").strip() == "1"
    return IntegrationSettings(
        gateway_url=os.environ.get("HAMMRLY_GATEWAY_URL", "http://localhost:8080").rstrip("/"),
        query_url=os.environ.get("HAMMRLY_QUERY_URL", "http://localhost:8081").rstrip("/"),
        jwt_secret=os.environ.get(
            "HAMMRLY_JWT_DEV_HMAC_SECRET",
            "dev-hammrly-jwt-secret-min-32b!!",
        ),
        tenant_id=os.environ.get("HAMMRLY_INTEGRATION_TENANT", "demo-tenant"),
        project_id=os.environ.get("HAMMRLY_INTEGRATION_PROJECT", "integration-tests"),
        notebook_image=os.environ.get(
            "HAMMRLY_NOTEBOOK_IMAGE",
            "jupyter/minimal-notebook:latest",
        ),
        desktop_image=os.environ.get("HAMMRLY_DESKTOP_IMAGE", "").strip() or None,
        poll_timeout_sec=float(os.environ.get("HAMMRLY_INTEGRATION_TIMEOUT_SEC", "900")),
        tls_verify=not insecure,
    )

_TERMINAL_FAILURE_STATUSES = frozenset[str](
    {
        "failed",
        "unknown",
        "succeeded",
    }
)


def integration_token(
    settings: IntegrationSettings,
    *,
    scope: str = "hammrly:jobs:submit hammrly:jobs:read aarc",
    sub: str = "integration-user",
) -> str:
    claims: dict[str, Any] = {
        "sub": sub,
        "hammrly_tenant_id": settings.tenant_id,
        "scope": scope,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def notebook_workload(
    settings: IntegrationSettings,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    session_name = name or f"integration-notebook-{uuid.uuid4().hex[:12]}"
    return {
        "kind": "notebook",
        "name": session_name,
        "image": settings.notebook_image,
        "resources": {
            "cpu": "2",
            "memory": "4Gi",
        },
        "kind_options": {
            "jupyter": {"port": 8888},
        },
    }


def desktop_workload(
    settings: IntegrationSettings,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    if not settings.desktop_image:
        raise ValueError("HAMMRLY_DESKTOP_IMAGE is required for desktop integration tests")
    session_name = name or f"integration-desktop-{uuid.uuid4().hex[:12]}"
    return {
        "kind": "desktop",
        "name": session_name,
        "image": settings.desktop_image,
        "resources": {
            "cpu": "4",
            "memory": "8Gi",
        },
        "kind_options": {
            "novnc": {"port": 6080},
        },
    }


def submit_desktop_session(
    client: httpx.Client,
    settings: IntegrationSettings,
    token: str,
) -> dict[str, Any]:
    body = {
        "project_id": settings.project_id,
        "workload": desktop_workload(settings),
    }
    r = client.post(
        f"{settings.gateway_url}/v2/session",
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 202, r.text
    data = r.json()
    assert data.get("status") == "PENDING"
    assert "job_id" in data and "submission_id" in data
    return data


def submit_notebook_session(
    client: httpx.Client,
    settings: IntegrationSettings,
    token: str,
) -> dict[str, Any]:
    body = {
        "project_id": settings.project_id,
        "workload": notebook_workload(settings),
    }
    r = client.post(
        f"{settings.gateway_url}/v2/session",
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 202, r.text
    data = r.json()
    assert data.get("status") == "PENDING"
    assert "job_id" in data and "submission_id" in data
    return data


def poll_job_until_ready(
    client: httpx.Client,
    settings: IntegrationSettings,
    job_id: str,
    token: str,
) -> dict[str, Any]:
    """Poll Query until status is ready or a terminal failure is observed."""
    delay = 1.0
    deadline = time.monotonic() + settings.poll_timeout_sec
    last: dict[str, Any] | None = None

    while time.monotonic() < deadline:
        r = client.get(
            f"{settings.query_url}/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code == 404:
            time.sleep(delay)
            delay = min(delay * 1.5, 5.0)
            continue
        assert r.status_code == 200, r.text
        last = r.json()
        status = last.get("status")
        logger.info("poll_job_until_ready: status: %s", status)
        if status == "ready":
            return last
        if status in _TERMINAL_FAILURE_STATUSES:
            raise AssertionError(
                f"job {job_id} reached terminal status {status!r} before ready: {last!r}"
            )
        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)

    raise TimeoutError(
        f"job {job_id} did not reach status 'ready' within {settings.poll_timeout_sec}s; "
        f"last response: {last!r}"
    )


def assert_access_url_reachable(client: httpx.Client, access_url: str) -> None:
    """GET the session access URL and require a successful HTTP response."""
    assert access_url and access_url.strip(), "access_url must be set when status is ready"
    r = client.get(access_url)
    assert r.is_success, (
        f"access_url {access_url!r} returned {r.status_code}; body prefix: {r.text[:500]!r}"
    )
