from __future__ import annotations

from hammrly_orchestrator.k8s.workload_error import (
    parse_error_json,
    parse_workload_error_from_log_text,
    status_detail_from_error,
)


def test_parse_error_manifest_direct():
    err = parse_error_json(
        '{"status":"error","code":"processing_failed","message":"No sources"}'
    )
    assert err is not None
    assert err["code"] == "processing_failed"
    assert status_detail_from_error(err) == "processing_failed: No sources"


def test_parse_sidecar_wrapper():
    err = parse_error_json(
        '{"payload":{"status":"error","code":"x","message":"y"},"status":"error"}'
    )
    assert err is not None
    assert err["code"] == "x"


def test_parse_marker_from_logs():
    text = "\n".join(
        [
            "Waiting...",
            'HAMMRLY_WORKLOAD_ERROR={"status":"error","code":"boom","message":"bad"}',
            "exit",
        ]
    )
    err = parse_workload_error_from_log_text(text)
    assert err is not None
    assert err["code"] == "boom"
