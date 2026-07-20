from __future__ import annotations

from hammrly_orchestrator.campaign.merge import build_job_envelope, merge_item_to_workload, resolve_uri_placeholders


def test_resolve_uri_placeholders() -> None:
    uri = resolve_uri_placeholders(
        "s3://b/{project_id}/{campaign_id}/{item_key}/",
        campaign_id="c1",
        item_key="tile-1",
        project_id="proj",
    )
    assert uri == "s3://b/proj/c1/tile-1/"


def test_merge_batch_args_replace() -> None:
    template = {
        "kind": "headless",
        "name": "t",
        "image": "img:1",
        "resources": {"cpu": "1"},
        "kind_options": {"batch": {"command": ["python"], "args": ["base"]}},
    }
    item = {"item_key": "a", "input_uri": "https://in", "batch_args": ["--x"]}
    wl = merge_item_to_workload(
        template,
        item,
        campaign={"output_uri": "https://out/{item_key}/"},
        campaign_id="cid",
        project_id=None,
    )
    assert wl["kind_options"]["batch"]["args"] == ["--x"]
    assert wl["output_uri"] == "https://out/a/"


def test_build_job_envelope_has_campaign_id() -> None:
    camp = {
        "campaign_id": "550e8400-e29b-41d4-a716-446655440099",
        "tenant_id": "t",
        "user_id": "u",
        "requested_at": "2026-05-30T12:00:00Z",
        "campaign": {"name": "n"},
        "template": {
            "kind": "headless",
            "name": "t",
            "image": "img",
            "resources": {"cpu": "1"},
            "kind_options": {"batch": {"command": ["c"]}},
        },
    }
    env = build_job_envelope(
        camp,
        {"item_key": "k1", "input_uri": "https://in"},
        submission_id="660e8400-e29b-41d4-a716-446655440001",
        job_id="770e8400-e29b-41d4-a716-446655440002",
    )
    assert env["campaign_id"] == camp["campaign_id"]
    assert env["workload"]["input_uri"] == "https://in"
