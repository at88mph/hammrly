from __future__ import annotations

import json
from typing import Any

from hammrly_orchestrator.campaign.merge import build_job_envelope


def build_items_manifest_document(
    campaign_envelope: dict[str, Any],
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build ordered items manifest for JobSet indexed pods.

    Each entry has submission_id, job_id, item_key, completion_index, and merged workload.
    """
    campaign_id = str(campaign_envelope["campaign_id"])
    items_out: list[dict[str, Any]] = []
    for entry in entries:
        idx = int(entry["completion_index"])
        item = entry["item"]
        job_env = build_job_envelope(
            campaign_envelope,
            item,
            submission_id=str(entry["submission_id"]),
            job_id=str(entry["job_id"]),
        )
        row: dict[str, Any] = {
            "completion_index": idx,
            "item_key": str(item["item_key"]),
            "submission_id": str(entry["submission_id"]),
            "job_id": str(entry["job_id"]),
            "workload": job_env["workload"],
        }
        item_env = item.get("env")
        if isinstance(item_env, dict):
            row["env"] = {str(k): str(v) for k, v in item_env.items() if isinstance(k, str)}
        items_out.append(row)
    return {
        "schema_version": "1.0",
        "campaign_id": campaign_id,
        "items": items_out,
    }


def serialize_items_manifest(doc: dict[str, Any]) -> bytes:
    return json.dumps(doc, separators=(",", ":"), sort_keys=True).encode("utf-8")
