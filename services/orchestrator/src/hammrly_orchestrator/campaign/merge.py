from __future__ import annotations

import copy
from typing import Any, Optional


def resolve_uri_placeholders(
    uri: str,
    *,
    campaign_id: str,
    item_key: str,
    project_id: Optional[str],
) -> str:
    out = uri
    out = out.replace("{campaign_id}", campaign_id)
    out = out.replace("{item_key}", item_key)
    if project_id:
        out = out.replace("{project_id}", project_id)
    else:
        out = out.replace("{project_id}/", "").replace("/{project_id}", "")
    return out


def merge_item_to_workload(
    template: dict[str, Any],
    item: dict[str, Any],
    *,
    campaign: dict[str, Any],
    campaign_id: str,
    project_id: Optional[str],
) -> dict[str, Any]:
    wl = copy.deepcopy(template)
    if item.get("name"):
        wl["name"] = str(item["name"])

    input_uri = item.get("input_uri")
    if input_uri:
        wl["input_uri"] = str(input_uri)

    output_uri = item.get("output_uri") or campaign.get("output_uri") or template.get("output_uri")
    if output_uri:
        wl["output_uri"] = resolve_uri_placeholders(
            str(output_uri),
            campaign_id=campaign_id,
            item_key=str(item["item_key"]),
            project_id=project_id,
        )

    ko = wl.get("kind_options")
    if not isinstance(ko, dict):
        ko = {}
        wl["kind_options"] = ko
    batch = ko.get("batch")
    if not isinstance(batch, dict):
        batch = {}
        ko["batch"] = batch
    if item.get("batch_args") is not None:
        batch["args"] = list(item["batch_args"])

    labels: dict[str, str] = {}
    camp_labels = campaign.get("labels")
    if isinstance(camp_labels, dict):
        for k, v in camp_labels.items():
            if isinstance(k, str) and isinstance(v, str):
                labels[k] = v
    tpl_labels = template.get("labels")
    if isinstance(tpl_labels, dict):
        for k, v in tpl_labels.items():
            if isinstance(k, str) and isinstance(v, str):
                labels[k] = v
    item_labels = item.get("labels")
    if isinstance(item_labels, dict):
        for k, v in item_labels.items():
            if isinstance(k, str) and isinstance(v, str):
                labels[k] = v
    if labels:
        wl["labels"] = labels

    return wl


def build_job_envelope(
    campaign_envelope: dict[str, Any],
    item: dict[str, Any],
    *,
    submission_id: str,
    job_id: str,
) -> dict[str, Any]:
    campaign_id = str(campaign_envelope["campaign_id"])
    project_id = campaign_envelope.get("project_id")
    if project_id is not None:
        project_id = str(project_id).strip() or None
    workload = merge_item_to_workload(
        campaign_envelope["template"],
        item,
        campaign=campaign_envelope["campaign"],
        campaign_id=campaign_id,
        project_id=project_id,
    )
    env: dict[str, Any] = {
        "schema_version": "1.0",
        "submission_id": submission_id,
        "job_id": job_id,
        "tenant_id": campaign_envelope["tenant_id"],
        "user_id": campaign_envelope["user_id"],
        "requested_at": campaign_envelope["requested_at"],
        "workload": workload,
        "campaign_id": campaign_id,
    }
    if project_id:
        env["project_id"] = project_id
    if campaign_envelope.get("correlation"):
        env["correlation"] = campaign_envelope["correlation"]
    return env
