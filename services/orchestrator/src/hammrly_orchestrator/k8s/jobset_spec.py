from __future__ import annotations

import copy
from typing import Any


def campaign_template_for_indexed_job(template: dict[str, Any]) -> dict[str, Any]:
    """Strip per-item URIs from the shared template used for indexed JobSet pods."""
    wl = copy.deepcopy(template)
    wl.pop("input_uri", None)
    wl.pop("output_uri", None)
    return wl


def batch_parallelism(template: dict[str, Any], *, item_count: int) -> int:
    ko = template.get("kind_options")
    if not isinstance(ko, dict):
        return 1
    batch = ko.get("batch")
    if not isinstance(batch, dict):
        return 1
    raw = batch.get("parallelism")
    try:
        p = int(raw) if raw is not None else 1
    except (TypeError, ValueError):
        p = 1
    return max(1, min(p, item_count))


def batch_backoff_limit(template: dict[str, Any]) -> int | None:
    ko = template.get("kind_options")
    if not isinstance(ko, dict):
        return None
    batch = ko.get("batch")
    if not isinstance(batch, dict):
        return None
    raw = batch.get("backoff_limit")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
