from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from kubernetes.client import V1Job

from hammrly_orchestrator.k8s.labels import LABEL_JOB_ID, LABEL_SUBMISSION_ID, LABEL_USER_ID


def _job_counts(job: V1Job) -> dict[str, int]:
    status = job.status
    return {
        "active": int(status.active or 0) if status else 0,
        "succeeded": int(status.succeeded or 0) if status else 0,
        "failed": int(status.failed or 0) if status else 0,
    }


def condition_summaries(job: V1Job) -> list[dict[str, Any]]:
    status = job.status
    conditions = list(status.conditions or []) if status else []
    out: list[dict[str, Any]] = []
    for c in conditions:
        out.append(
            {
                "type": getattr(c, "type", None),
                "status": getattr(c, "status", None),
                "reason": getattr(c, "reason", None),
                "message": (str(getattr(c, "message", None))[:1000] if getattr(c, "message", None) else None),
            }
        )
    return out


def watch_event_payload(
    job: V1Job,
    *,
    label_job_id: Optional[str] = None,
    status_detail: Optional[str] = None,
) -> dict[str, Any]:
    meta = job.metadata
    rv = meta.resource_version if meta else None
    spec = job.spec
    payload: dict[str, Any] = {
        "resource_version": rv,
        "label_job_id": label_job_id,
        "counts": _job_counts(job),
        "suspend": getattr(spec, "suspend", None) if spec else None,
        "conditions": condition_summaries(job),
    }
    if status_detail:
        payload["status_detail"] = status_detail[:2000]
    return payload


def map_job_to_submission_status(job: V1Job) -> tuple[str, Optional[str]]:
    """
    Map Kubernetes Job state to submissions.status / status_detail.

    Returns (status, status_detail).
    """
    status = job.status
    conditions = list(status.conditions or []) if status else []

    for c in conditions:
        if getattr(c, "type", None) == "Complete" and getattr(c, "status", None) == "True":
            return "succeeded", None
        if getattr(c, "type", None) == "Failed" and getattr(c, "status", None) == "True":
            msg = getattr(c, "message", None) or getattr(c, "reason", None)
            return "failed", str(msg) if msg else None

    spec = job.spec
    spec_suspend = getattr(spec, "suspend", None) if spec else None
    counts = _job_counts(job)
    active = counts["active"]
    failed_ct = counts["failed"]

    if active > 0:
        return "running", None

    if failed_ct > 0:
        return "failed", f"{failed_ct} failed pod(s)"

    if spec_suspend is True:
        return "submitted_to_cluster", None

    # Unsuspended, no active pods yet — admitted / scheduling
    if spec_suspend is False:
        return "admitted", None

    return "submitted_to_cluster", None


def labels_from_job(job: V1Job) -> dict[str, str]:
    meta = job.metadata
    if not meta or not meta.labels:
        return {}
    return dict(meta.labels)


def submission_id_from_job(job: V1Job) -> Optional[str]:
    return labels_from_job(job).get(LABEL_SUBMISSION_ID)


def job_id_from_job(job: V1Job) -> Optional[str]:
    return labels_from_job(job).get(LABEL_JOB_ID)


def user_id_from_job(job: V1Job) -> Optional[str]:
    return labels_from_job(job).get(LABEL_USER_ID)


def resource_version(job: V1Job) -> Optional[str]:
    meta = job.metadata
    if not meta:
        return None
    return meta.resource_version


def job_uid(job: V1Job) -> Optional[str]:
    meta = job.metadata
    if not meta:
        return None
    return meta.uid
