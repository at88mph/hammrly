from __future__ import annotations

from typing import Any

import jwt


def hs256_token(
    *,
    sub: str = "user-1",
    tenant: str = "tenant-z",
    scope: str | None = "hammrly:jobs:submit",
    secret: str = "gateway-unit-test-hmac-secret-at-least-32b",
) -> str:
    claims: dict[str, Any] = {"sub": sub, "hammrly_tenant_id": tenant}
    if scope is not None:
        claims["scope"] = scope
    return jwt.encode(claims, secret, algorithm="HS256")


def headless_workload() -> dict[str, Any]:
    return {
        "kind": "headless",
        "name": "batch-test",
        "image": "busybox:latest",
        "resources": {"cpu": "200m"},
        "kind_options": {"batch": {"command": ["sleep"], "args": ["1"]}},
    }


def campaign_submit_body(*, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if items is None:
        items = [
            {
                "item_key": "run-1",
                "input_uri": "https://data.example/input.fits",
            }
        ]
    return {
        "schema_version": "1.0",
        "campaign": {
            "name": "test-campaign",
            "output_uri": "https://storage.example/out/{item_key}/",
        },
        "template": headless_workload(),
        "items": items,
    }


def notebook_workload(*, name: str = "analysis-notebook") -> dict[str, Any]:
    return {
        "kind": "notebook",
        "name": name,
        "image": "jupyter/minimal-notebook:latest",
        "resources": {
            "cpu": "2",
            "memory": "4Gi",
        },
        "kind_options": {
            "jupyter": {"port": 8888},
        },
    }


def desktop_workload(*, with_networking_keys: bool = True) -> dict[str, Any]:
    w: dict[str, Any] = {
        "kind": "desktop",
        "name": "desk",
        "image": "registry.example/hammrly/desktop-astronomy:1.0",
        "resources": {
            "cpu": "4",
            "memory": "8Gi",
        },
        "kind_options": {
            "novnc": {"port": 6080},
        },
    }
    if with_networking_keys:
        w["needs_ingress"] = True
        w["needs_service"] = True
    return w
