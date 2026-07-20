from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

logger = logging.getLogger(__name__)


def _fetch_bytes(uri: str) -> bytes:
    parts = urlsplit(uri)
    if parts.scheme in ("http", "https"):
        with urlopen(uri, timeout=120) as resp:
            return resp.read()
    if parts.scheme == "file":
        path = Path(unquote(parts.path))
        return path.read_bytes()
    if not parts.scheme:
        return Path(uri).read_bytes()
    raise ValueError(f"unsupported manifest_uri scheme: {parts.scheme!r}")


def load_campaign_items(manifest_uri: str, *, expected_sha256: str | None = None) -> list[dict[str, Any]]:
    raw = _fetch_bytes(manifest_uri)
    if expected_sha256:
        digest = hashlib.sha256(raw).hexdigest()
        if digest.lower() != expected_sha256.lower():
            raise ValueError("manifest_sha256 mismatch")
    text = raw.decode("utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("{"):
        doc = json.loads(stripped)
        items = doc.get("items") if isinstance(doc, dict) else None
        if not isinstance(items, list):
            raise ValueError("manifest JSON must contain items array")
        return [it for it in items if isinstance(it, dict)]
    items: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"manifest JSONL line {line_no}: {e}") from e
        if not isinstance(row, dict):
            raise ValueError(f"manifest JSONL line {line_no}: expected object")
        items.append(row)
    return items
