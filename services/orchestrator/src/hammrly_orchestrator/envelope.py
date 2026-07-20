from __future__ import annotations

import json
from typing import Any


class EnvelopeParseError(ValueError):
    """Payload could not be parsed or failed contract checks."""

    def __init__(self, message: str, raw_preview: str | None = None) -> None:
        super().__init__(message)
        self.raw_preview = raw_preview


def _decode_payload(raw: str | bytes | memoryview) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    raise EnvelopeParseError(f"Unexpected payload type: {type(raw)}")


def parse_stream_payload(raw: str | bytes | memoryview) -> dict[str, Any]:
    text = _decode_payload(raw).strip()
    if not text:
        raise EnvelopeParseError("Empty payload")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise EnvelopeParseError(f"Invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise EnvelopeParseError("Envelope must be a JSON object")
    return data


def validate_envelope_minimal(data: dict[str, Any], *, accepted_schema_major: int) -> None:
    """Apply light validation before JSON Schema tooling is wired in."""

    for key in (
        "schema_version",
        "submission_id",
        "job_id",
        "tenant_id",
        "user_id",
        "requested_at",
        "workload",
    ):
        if key not in data:
            raise EnvelopeParseError(f"Missing required field: {key}")

    sv = data["schema_version"]
    if not isinstance(sv, str) or "." not in sv:
        raise EnvelopeParseError("schema_version must be a major.minor string")

    major_str, _sep, _minor = sv.partition(".")
    try:
        major = int(major_str)
    except ValueError as e:
        raise EnvelopeParseError("schema_version major must be an integer") from e

    if major != accepted_schema_major:
        raise EnvelopeParseError(
            f"Unsupported schema major {major}; this listener accepts major {accepted_schema_major} only"
        )

    if not isinstance(data["job_id"], str) or not data["job_id"].strip():
        raise EnvelopeParseError("job_id must be a non-empty string")

    if not isinstance(data["user_id"], str) or not data["user_id"].strip():
        raise EnvelopeParseError("user_id must be a non-empty string")

    workload = data["workload"]
    if not isinstance(workload, dict):
        raise EnvelopeParseError("workload must be an object")

    for wkey in ("kind", "name", "image", "resources"):
        if wkey not in workload:
            raise EnvelopeParseError(f"workload missing required field: {wkey}")

    gc = workload.get("gpu_count")
    if gc is not None:
        if isinstance(gc, bool):
            raise EnvelopeParseError("workload.gpu_count must be an integer")
        if not isinstance(gc, int):
            raise EnvelopeParseError("workload.gpu_count must be an integer")
        if gc < 0:
            raise EnvelopeParseError("workload.gpu_count must be >= 0")


def validate_campaign_envelope_minimal(data: dict[str, Any], *, accepted_schema_major: int) -> None:
    for key in (
        "schema_version",
        "campaign_id",
        "tenant_id",
        "user_id",
        "requested_at",
        "campaign",
        "template",
    ):
        if key not in data:
            raise EnvelopeParseError(f"Missing required field: {key}")

    sv = data["schema_version"]
    if not isinstance(sv, str) or "." not in sv:
        raise EnvelopeParseError("schema_version must be a major.minor string")
    major_str, _sep, _minor = sv.partition(".")
    try:
        major = int(major_str)
    except ValueError as e:
        raise EnvelopeParseError("schema_version major must be an integer") from e
    if major != accepted_schema_major:
        raise EnvelopeParseError(
            f"Unsupported schema major {major}; this listener accepts major {accepted_schema_major} only"
        )

    if not isinstance(data.get("items"), list) and not data.get("manifest_uri"):
        raise EnvelopeParseError("campaign envelope requires items or manifest_uri")

    template = data["template"]
    if not isinstance(template, dict) or template.get("kind") != "headless":
        raise EnvelopeParseError("template.kind must be headless")
