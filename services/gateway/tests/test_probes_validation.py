"""Gateway validation for kind_options.probes."""
from __future__ import annotations

import pytest

from hammrly_gateway.validation import cross_validate_envelope, load_validator, validate_envelope


def _base_envelope(workload: dict) -> dict:
    return {
        "schema_version": "1.0",
        "submission_id": "660e8400-e29b-41d4-a716-446655440001",
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "tenant_id": "t1",
        "user_id": "u1",
        "requested_at": "2026-01-01T00:00:00Z",
        "workload": workload,
    }


def test_schema_accepts_notebook_probes() -> None:
    load_validator()
    env = _base_envelope(
        {
            "kind": "notebook",
            "name": "nb",
            "image": "jupyter/minimal-notebook:latest",
            "resources": {"cpu": "100m"},
            "needs_service": True,
            "needs_ingress": True,
            "kind_options": {
                "jupyter": {"port": 8888},
                "probes": {
                    "readiness": {
                        "httpGet": {"path": "{ingress_path}/readyz", "port": "workload"},
                    },
                },
            },
        },
    )
    validate_envelope(env)


def test_contributed_requires_readiness_probe() -> None:
    env = _base_envelope(
        {
            "kind": "contributed",
            "name": "app",
            "image": "my/app:latest",
            "resources": {"cpu": "100m"},
            "needs_service": True,
            "needs_ingress": True,
            "kind_options": {"contributed": {"command": ["python", "-m", "http.server"]}},
        },
    )
    with pytest.raises(ValueError, match="probes.readiness"):
        cross_validate_envelope(env)


def test_contributed_with_readiness_probe_ok() -> None:
    env = _base_envelope(
        {
            "kind": "contributed",
            "name": "app",
            "image": "my/app:latest",
            "resources": {"cpu": "100m"},
            "needs_service": True,
            "needs_ingress": True,
            "kind_options": {
                "contributed": {"command": ["python", "-m", "http.server"]},
                "probes": {
                    "readiness": {"httpGet": {"path": "/", "port": "workload"}},
                },
            },
        },
    )
    cross_validate_envelope(env)
