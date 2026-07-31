from __future__ import annotations

from types import SimpleNamespace

from hammrly_orchestrator.k8s.job_state import map_job_to_submission_status, watch_event_payload


def _job(*, failed=None, active=None, conditions=None, suspend=False, rv="12"):
    return SimpleNamespace(
        metadata=SimpleNamespace(resource_version=rv, labels={}),
        spec=SimpleNamespace(suspend=suspend),
        status=SimpleNamespace(
            failed=failed,
            active=active,
            succeeded=None,
            conditions=conditions or [],
        ),
    )


def test_map_failed_condition_includes_message():
    cond = SimpleNamespace(type="Failed", status="True", reason="BackoffLimitExceeded", message="Job has reached the specified backoff limit")
    status, detail = map_job_to_submission_status(_job(conditions=[cond]))
    assert status == "failed"
    assert detail and "backoff" in detail.lower()


def test_watch_event_payload_includes_conditions_and_counts():
    cond = SimpleNamespace(type="Failed", status="True", reason="Err", message="boom")
    job = _job(failed=1, conditions=[cond], rv="99")
    payload = watch_event_payload(job, label_job_id="jid", status_detail="boom")
    assert payload["resource_version"] == "99"
    assert payload["counts"]["failed"] == 1
    assert payload["conditions"][0]["message"] == "boom"
    assert payload["status_detail"] == "boom"
