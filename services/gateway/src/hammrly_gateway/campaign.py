from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from hammrly_gateway.config import Settings
from hammrly_gateway.envelope import canonical_body_hash
from hammrly_gateway.jwt_auth import Principal
from hammrly_gateway.validation import (
    cross_validate_envelope,
    normalize_workload_ephemeral_storage,
    normalize_workload_networking,
    validation_error_message,
    validate_envelope,
)

_ITEM_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CAMPAIGN_SCHEMA: Optional[dict[str, Any]] = None
_CAMPAIGN_VALIDATOR: Optional[Draft202012Validator] = None


def _default_campaign_schema_path() -> Path:
    here = Path(__file__).resolve().parent
    root = here.parent.parent.parent.parent
    p = root / "contracts" / "job-campaign" / "v1" / "schema.json"
    if p.is_file():
        return p
    return Path("contracts/job-campaign/v1/schema.json")


def load_campaign_validator(schema_path: Optional[str] = None) -> Draft202012Validator:
    global _CAMPAIGN_SCHEMA, _CAMPAIGN_VALIDATOR
    path = Path(schema_path) if schema_path else _default_campaign_schema_path()
    if not path.is_file():
        raise FileNotFoundError(f"Campaign schema not found: {path}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    submit = schema["$defs"]["CampaignSubmitRequest"]
    Draft202012Validator.check_schema(submit)
    _CAMPAIGN_SCHEMA = schema
    _CAMPAIGN_VALIDATOR = Draft202012Validator(submit)
    return _CAMPAIGN_VALIDATOR


def get_campaign_validator(schema_path: Optional[str] = None) -> Draft202012Validator:
    if _CAMPAIGN_VALIDATOR is not None and not schema_path:
        return _CAMPAIGN_VALIDATOR
    return load_campaign_validator(schema_path)


def validate_campaign_submit(body: dict[str, Any], *, schema_path: Optional[str] = None) -> None:
    get_campaign_validator(schema_path).validate(body)


def cross_validate_campaign_submit(
    body: dict[str, Any],
    *,
    max_inline_items: int,
) -> None:
    template = body.get("template")
    if not isinstance(template, dict) or template.get("kind") != "headless":
        raise ValueError("template.kind must be headless")

    items = body.get("items")
    manifest_uri = body.get("manifest_uri")
    if items is not None and manifest_uri is not None:
        raise ValueError("provide either items or manifest_uri, not both")
    if items is None and not manifest_uri:
        raise ValueError("either items or manifest_uri is required")

    if items is not None:
        if not isinstance(items, list) or len(items) < 1:
            raise ValueError("items must contain at least one entry")
        if len(items) > max_inline_items:
            raise ValueError(
                f"inline items count {len(items)} exceeds maximum {max_inline_items}; use manifest_uri"
            )
        seen: set[str] = set()
        for it in items:
            if not isinstance(it, dict):
                raise ValueError("each item must be an object")
            key = it.get("item_key")
            if not isinstance(key, str) or not _ITEM_KEY_RE.fullmatch(key):
                raise ValueError(f"invalid item_key: {key!r}")
            if key in seen:
                raise ValueError(f"duplicate item_key: {key}")
            seen.add(key)

    # Validate template as workload for job-submission rules
    fake_envelope = {
        "schema_version": "1.0",
        "submission_id": "00000000-0000-0000-0000-000000000001",
        "job_id": "00000000-0000-0000-0000-000000000002",
        "tenant_id": "validation",
        "user_id": "validation",
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "workload": template,
    }
    cross_validate_envelope(fake_envelope)


def normalize_campaign_body(
    body: dict[str, Any],
    *,
    ephemeral_default: str,
    ephemeral_max: str,
) -> dict[str, Any]:
    out = copy.deepcopy(body)
    tpl = normalize_workload_networking(out["template"])
    tpl = normalize_workload_ephemeral_storage(
        tpl,
        default_request=ephemeral_default,
        maximum=ephemeral_max,
    )
    out["template"] = tpl
    return out


def build_campaign_expansion_envelope(
    *,
    settings: Settings,
    principal: Principal,
    tenant_id: str,
    body: dict[str, Any],
    campaign_id: UUID,
) -> dict[str, Any]:
    corr = body.get("correlation")
    items = body.get("items")
    item_count: Optional[int] = len(items) if isinstance(items, list) else body.get("item_count")
    env: dict[str, Any] = {
        "schema_version": settings.campaign_schema_version,
        "campaign_id": str(campaign_id),
        "tenant_id": tenant_id,
        "user_id": principal.user_id,
        "requested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "campaign": body["campaign"],
        "template": body["template"],
    }
    project_id = body.get("project_id")
    if project_id is not None:
        env["project_id"] = str(project_id).strip() or None
    if corr:
        env["correlation"] = corr
    if items is not None:
        env["items"] = items
    if body.get("manifest_uri"):
        env["manifest_uri"] = body["manifest_uri"]
    if body.get("manifest_sha256"):
        env["manifest_sha256"] = body["manifest_sha256"]
    if item_count is not None:
        env["item_count"] = int(item_count)
    return env


def campaign_body_hash(body: dict[str, Any]) -> str:
    return canonical_body_hash(body)


def reject_headless_on_session(workload: dict[str, Any]) -> None:
    if workload.get("kind") == "headless":
        raise ValueError(
            "workload.kind=headless must be submitted via POST /v2/campaigns (not /v2/session)"
        )


__all__ = [
    "build_campaign_expansion_envelope",
    "campaign_body_hash",
    "cross_validate_campaign_submit",
    "load_campaign_validator",
    "normalize_campaign_body",
    "reject_headless_on_session",
    "validate_campaign_submit",
    "validation_error_message",
]
