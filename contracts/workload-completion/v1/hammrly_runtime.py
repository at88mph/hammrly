#!/usr/bin/env python3
"""Small stdlib-only helper for writing Hammrly workload completion manifests.

Image authors can vendor this file or fetch it over HTTP during image builds.

Example:

    from hammrly_runtime import complete, fail

    complete(outputs=["outputs/result.fits"])
    fail(code="processing_failed", message="No sources detected")
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

SCHEMA_VERSION = "1.0"
DEFAULT_WORKSPACE = "/workspace"
DEFAULT_COMPLETION_FILE = "hammrly-complete.json"
DEFAULT_ERROR_FILE = "hammrly-error.json"


def workspace_path() -> Path:
    return Path(os.environ.get("HAMMRLY_WORKSPACE", DEFAULT_WORKSPACE))


def completion_file_path() -> Path:
    return _env_path("HAMMRLY_COMPLETION_FILE", workspace_path() / DEFAULT_COMPLETION_FILE)


def error_file_path() -> Path:
    return _env_path("HAMMRLY_ERROR_FILE", workspace_path() / DEFAULT_ERROR_FILE)


def complete(
    outputs: Optional[Sequence[Union[str, Mapping[str, Any]]]] = None,
    *,
    metadata: Optional[Mapping[str, Any]] = None,
    path: Optional[Union[str, os.PathLike[str]]] = None,
) -> dict[str, Any]:
    """Write the success manifest and return the JSON payload."""
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "complete",
        "finished_at": _now_rfc3339(),
        "outputs": [_normalize_output(o) for o in (outputs or [])],
    }
    if metadata:
        payload["metadata"] = dict(metadata)
    _atomic_write_json(Path(path) if path is not None else completion_file_path(), payload)
    return payload


def fail(
    code: str,
    message: str,
    *,
    details: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    path: Optional[Union[str, os.PathLike[str]]] = None,
) -> dict[str, Any]:
    """Write the error manifest and return the JSON payload."""
    if not str(code).strip():
        raise ValueError("code must be non-empty")
    if not str(message).strip():
        raise ValueError("message must be non-empty")

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "error",
        "finished_at": _now_rfc3339(),
        "code": str(code),
        "message": str(message),
    }
    if details:
        payload["details"] = dict(details)
    if metadata:
        payload["metadata"] = dict(metadata)
    _atomic_write_json(Path(path) if path is not None else error_file_path(), payload)
    return payload


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else default


def _now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_output(output: Union[str, Mapping[str, Any]]) -> Union[str, dict[str, Any]]:
    if isinstance(output, str):
        if not output.strip():
            raise ValueError("output path strings must be non-empty")
        return output

    item = dict(output)
    path = str(item.get("path", "")).strip()
    if not path:
        raise ValueError("output objects must include a non-empty 'path'")
    item["path"] = path
    return item


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _parse_metadata(values: Sequence[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for value in values:
        key, sep, raw = value.partition("=")
        if not sep or not key:
            raise SystemExit(f"metadata must be KEY=VALUE, got: {value!r}")
        out[key] = raw
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Write Hammrly workload completion manifests.")
    sub = parser.add_subparsers(dest="command", required=True)

    complete_p = sub.add_parser("complete", help="write HAMMRLY_COMPLETION_FILE")
    complete_p.add_argument("outputs", nargs="*", help="output file paths to upload")
    complete_p.add_argument("--metadata", action="append", default=[], metavar="KEY=VALUE")
    complete_p.add_argument("--path", help="override manifest path")

    fail_p = sub.add_parser("fail", help="write HAMMRLY_ERROR_FILE")
    fail_p.add_argument("code")
    fail_p.add_argument("message")
    fail_p.add_argument("--detail", action="append", default=[], metavar="KEY=VALUE")
    fail_p.add_argument("--metadata", action="append", default=[], metavar="KEY=VALUE")
    fail_p.add_argument("--path", help="override manifest path")

    args = parser.parse_args(argv)
    if args.command == "complete":
        payload = complete(
            outputs=args.outputs,
            metadata=_parse_metadata(args.metadata),
            path=args.path,
        )
    else:
        payload = fail(
            code=args.code,
            message=args.message,
            details=_parse_metadata(args.detail),
            metadata=_parse_metadata(args.metadata),
            path=args.path,
        )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
