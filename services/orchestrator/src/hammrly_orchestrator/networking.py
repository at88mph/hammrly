from __future__ import annotations

from typing import Any

_INTERACTIVE_KINDS = frozenset({"desktop", "notebook", "carta"})


def normalize_workload_networking(workload: dict[str, Any]) -> dict[str, Any]:
    """Mirror gateway: apply defaults for missing needs_service / needs_ingress (VALIDATION.md)."""
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

    if ns is None and ni is None:
        wl["needs_service"] = False
        wl["needs_ingress"] = False
    elif ns is None:
        wl["needs_service"] = True if ni is True else False
    elif ni is None:
        wl["needs_ingress"] = True if ns is True else False
    return wl
