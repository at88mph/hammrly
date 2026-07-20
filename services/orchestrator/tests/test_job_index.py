from __future__ import annotations

import json

import fakeredis

from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.job_index import index_key, update_job_index_after_received


def _sample_envelope() -> dict:
    return {
        "schema_version": "1.0",
        "submission_id": "660e8400-e29b-41d4-a716-446655440001",
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "tenant_id": "tenant-z",
        "user_id": "user-1",
        "requested_at": "2026-01-15T12:00:00Z",
        "workload": {
            "kind": "desktop",
            "name": "sess",
            "image": "img:latest",
            "gpu_count": 0,
            "needs_ingress": True,
            "needs_service": True,
        },
    }


def test_update_job_index_after_received_sets_received() -> None:
    settings = Settings(database_url="postgresql+psycopg2://u:p@localhost/db")
    r = fakeredis.FakeRedis(decode_responses=False)
    envelope = _sample_envelope()
    pending = json.dumps({"status": "pending"}).encode()
    r.set(index_key(settings, envelope["job_id"]), pending)

    update_job_index_after_received(r, settings, envelope, queue_name="desktop-q")

    raw = r.get(index_key(settings, envelope["job_id"]))
    assert raw is not None
    data = json.loads(raw.decode("utf-8"))
    assert data["status"] == "received"
    assert data["queue_name"] == "desktop-q"
    assert data["job_id"] == envelope["job_id"]
