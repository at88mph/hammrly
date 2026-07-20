from __future__ import annotations

import copy
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

_SCHEMA: Optional[dict[str, Any]] = None
_VALIDATOR: Optional[Draft202012Validator] = None

_EPHEMERAL_STORAGE_KEY = "ephemeral_storage"
_EPHEMERAL_STORAGE_K8S_KEY = "ephemeral-storage"
_EPHEMERAL_STORAGE_GB_RE = re.compile(r"^([+]?(?:\d+(?:\.\d*)?|\.\d+))(?:G|GB)?$", re.IGNORECASE)


def _default_contract_path() -> Path:
    here = Path(__file__).resolve().parent
    root = here.parent.parent.parent.parent
    p = root / "contracts" / "job-submission" / "v1" / "schema.json"
    if p.is_file():
        return p
    return Path("contracts/job-submission/v1/schema.json")


def load_validator(schema_path: Optional[str] = None) -> Draft202012Validator:
    global _SCHEMA, _VALIDATOR
    path = Path(schema_path) if schema_path else _default_contract_path()
    if not path.is_file():
        raise FileNotFoundError(f"Job submission schema not found: {path}")
    text = path.read_text(encoding="utf-8")
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    _SCHEMA = schema
    _VALIDATOR = Draft202012Validator(schema)
    return _VALIDATOR


def get_validator(schema_path: Optional[str] = None) -> Draft202012Validator:
    if _VALIDATOR is not None and not schema_path:
        return _VALIDATOR
    return load_validator(schema_path)


def validate_envelope(envelope: dict[str, Any], *, schema_path: Optional[str] = None) -> None:
    validator = get_validator(schema_path)
    validator.validate(envelope)


def validation_error_message(err: ValidationError) -> dict[str, Any]:
    return {
        "path": list(err.absolute_path),
        "validator": err.validator,
        "message": err.message,
    }


_INTERACTIVE_KINDS = frozenset({"desktop", "notebook", "carta", "firefly"})


def _format_gb_quantity(gb: Decimal) -> str:
    s = format(gb.normalize(), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return f"{s}G"


def _storage_gb_quantity(quantity: object) -> tuple[str, Decimal]:
    s = str(quantity).strip()
    if not s:
        raise ValueError("ephemeral storage GB value must be non-empty")
    m = _EPHEMERAL_STORAGE_GB_RE.fullmatch(s)
    if not m:
        raise ValueError(f"invalid ephemeral storage GB value: {s!r}")
    number_s = m.group(1)
    try:
        gb = Decimal(number_s)
    except InvalidOperation as e:
        raise ValueError(f"invalid ephemeral storage GB value: {s!r}") from e
    if gb <= 0:
        raise ValueError("ephemeral storage GB value must be greater than 0")
    return _format_gb_quantity(gb), gb


def normalize_workload_ephemeral_storage(
    workload: dict[str, Any],
    *,
    default_request: str,
    maximum: str,
) -> dict[str, Any]:
    """
    Apply platform ephemeral-storage defaults and caps.

    The public contract uses ``ephemeral_storage``; Kubernetes receives
    ``ephemeral-storage`` later when the orchestrator builds resources.
    """
    default_canon, default_gb = _storage_gb_quantity(default_request)
    _max_canon, max_gb = _storage_gb_quantity(maximum)
    if default_gb > max_gb:
        raise ValueError("default ephemeral storage exceeds configured maximum")

    wl = copy.deepcopy(workload)
    resources = wl.get("resources")
    if not isinstance(resources, dict):
        return wl

    if _EPHEMERAL_STORAGE_KEY in resources and _EPHEMERAL_STORAGE_K8S_KEY in resources:
        raise ValueError("use only workload.resources.ephemeral_storage, not both ephemeral_storage and ephemeral-storage")

    resources = dict(resources)
    wl["resources"] = resources

    if _EPHEMERAL_STORAGE_K8S_KEY in resources:
        resources[_EPHEMERAL_STORAGE_KEY] = resources.pop(_EPHEMERAL_STORAGE_K8S_KEY)

    value = resources.get(_EPHEMERAL_STORAGE_KEY)
    if value is None:
        resources[_EPHEMERAL_STORAGE_KEY] = default_canon
        return wl
    if isinstance(value, dict):
        raise ValueError(
            "workload.resources.ephemeral_storage must be a quantity string, not request/limit object"
        )

    canon, gb = _storage_gb_quantity(value)
    if gb > max_gb:
        raise ValueError("workload.resources.ephemeral_storage exceeds configured maximum")
    resources[_EPHEMERAL_STORAGE_KEY] = canon
    return wl


def normalize_workload_networking(workload: dict[str, Any]) -> dict[str, Any]:
    """
    Apply VALIDATION.md defaults for missing needs_service / needs_ingress.
    Returns a shallow copy; does not mutate the input.
    """
    wl = dict(workload)
    kind = wl.get("kind")
    if kind not in ("desktop", "notebook", "carta", "contributed", "headless"):
        raise ValueError("workload.kind must be set before networking normalization")

    ns = wl.get("needs_service")
    ni = wl.get("needs_ingress")

    if kind in _INTERACTIVE_KINDS:
        if ns is False or ni is False:
            raise ValueError(
                f"workload.kind={kind} requires needs_service=true and needs_ingress=true "
                "(explicit false is not allowed; omit the keys to use defaults)"
            )
        if ns is None:
            wl["needs_service"] = True
        if ni is None:
            wl["needs_ingress"] = True
        return wl

    if kind == "contributed":
        if ns is None and ni is None:
            wl["needs_service"] = True
            wl["needs_ingress"] = True
        elif ns is None:
            wl["needs_service"] = True if ni is True else False
        elif ni is None:
            wl["needs_ingress"] = True if ns is True else False
        return wl

    # headless
    if ns is None and ni is None:
        wl["needs_service"] = False
        wl["needs_ingress"] = False
    elif ns is None:
        wl["needs_service"] = True if ni is True else False
    elif ni is None:
        wl["needs_ingress"] = True if ns is True else False
    return wl


def _validate_resource_quantities(resources: dict[str, Any]) -> None:
    for key, value in resources.items():
        if isinstance(value, dict):
            raise ValueError(
                f"workload.resources.{key} must be a quantity string, not request/limit object"
            )


def cross_validate_envelope(envelope: dict[str, Any]) -> None:
    """Rules from contracts/job-submission/v1/VALIDATION.md."""
    wl = envelope.get("workload")
    if not isinstance(wl, dict):
        raise ValueError("workload must be an object")

    if wl.get("needs_ingress") and not wl.get("needs_service"):
        raise ValueError("needs_ingress requires needs_service to be true")

    kind = wl.get("kind")
    resources = wl.get("resources")
    if isinstance(resources, dict):
        _validate_resource_quantities(resources)
        has_res = bool(resources.get("cpu") or resources.get("memory"))
        has_gpu = False
        gpu_c = wl.get("gpu_count")
        if gpu_c is not None and not isinstance(gpu_c, bool):
            try:
                has_gpu = int(gpu_c) > 0
            except (TypeError, ValueError):
                pass
        nv = resources.get("nvidia.com/gpu")
        if not has_gpu and nv is not None and not isinstance(nv, dict):
            has_gpu = bool(str(nv).strip())
        if not has_res and not has_gpu:
            raise ValueError(
                "workload.resources should include cpu and/or memory and/or GPU quantity (see VALIDATION.md)"
            )

    if kind in ("desktop", "notebook", "carta"):
        if not wl.get("needs_service") or not wl.get("needs_ingress"):
            raise ValueError(
                f"workload.kind={kind} expects needs_service=true and needs_ingress=true "
                "(see VALIDATION.md)"
            )

    _validate_workload_probes(wl)


def _validate_workload_probes(wl: dict[str, Any]) -> None:
    """Probe rules from contracts/job-submission/v1/VALIDATION.md."""
    if not wl.get("needs_ingress"):
        return
    kind = wl.get("kind")
    if kind != "contributed":
        return
    ko = wl.get("kind_options")
    if not isinstance(ko, dict):
        raise ValueError(
            "workload.kind=contributed with needs_ingress=true requires "
            "kind_options.probes.readiness (see VALIDATION.md)"
        )
    probes = ko.get("probes")
    if not isinstance(probes, dict) or not isinstance(probes.get("readiness"), dict):
        raise ValueError(
            "workload.kind=contributed with needs_ingress=true requires "
            "kind_options.probes.readiness (see VALIDATION.md)"
        )
