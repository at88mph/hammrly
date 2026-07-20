from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from kubernetes.client import V1Job

from hammrly_orchestrator.k8s.labels import LABEL_JOB_ID, LABEL_SUBMISSION_ID, LABEL_USER_ID


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
    active = int(status.active or 0) if status else 0
    failed_ct = int(status.failed or 0) if status else 0

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
