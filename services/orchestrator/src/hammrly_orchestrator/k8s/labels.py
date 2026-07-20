from __future__ import annotations

import hashlib
import re
from typing import Any

# Per SPEC / Kueue docs: https://kueue.sigs.k8s.io/docs/reference/labels-and-annotations
LABEL_SUBMISSION_ID = "hammrly.io/submission-id"
LABEL_JOB_ID = "hammrly.io/job-id"
LABEL_TENANT_ID = "hammrly.io/tenant-id"
LABEL_USER_ID = "hammrly.io/user-id"
LABEL_WORKLOAD_KIND = "hammrly.io/workload-kind"
LABEL_CAMPAIGN_ID = "hammrly.io/campaign-id"
KUEUE_LOCAL_QUEUE_LABEL = "kueue.x-k8s.io/queue-name"

LABEL_MANAGED_BY = "hammrly.io/managed-by"
VALUE_MANAGED_BY_ORCHESTRATOR = "orchestrator"

_LABEL_VALUE_MAX_LEN = 63
# Kubernetes label value: optional empty; we require non-empty user_id upstream.
_VALID_LABEL_VALUE = re.compile(r"^[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?$")


def normalize_user_id_label_value(user_id: str) -> str:
    """Return a value valid for a Kubernetes label (≤63 chars, allowed charset)."""
    trimmed = user_id.strip()
    if not trimmed:
        raise ValueError("user_id is empty")

    if len(trimmed) <= _LABEL_VALUE_MAX_LEN and _VALID_LABEL_VALUE.fullmatch(trimmed):
        return trimmed

    digest = hashlib.sha256(trimmed.encode("utf-8")).hexdigest()[:32]
    candidate = f"u-{digest}"
    return candidate[:_LABEL_VALUE_MAX_LEN]


def normalize_job_id_label_value(job_id: str) -> str:
    """Kubernetes label value for hammrly.io/job-id (UUID-safe; hash if needed)."""
    trimmed = str(job_id).strip()
    if not trimmed:
        raise ValueError("job_id is empty")

    if len(trimmed) <= _LABEL_VALUE_MAX_LEN and _VALID_LABEL_VALUE.fullmatch(trimmed):
        return trimmed

    digest = hashlib.sha256(trimmed.encode("utf-8")).hexdigest()[:32]
    candidate = f"j-{digest}"
    return candidate[:_LABEL_VALUE_MAX_LEN]


def resource_names_from_submission(submission_id: str) -> tuple[str, str, str]:
    """Derive RFC 1123 names for Job, Service, Ingress from submission UUID."""
    compact = submission_id.replace("-", "").lower()
    if len(compact) != 32:
        # Still produce a bounded name if format ever relaxes
        digest = hashlib.sha256(submission_id.encode("utf-8")).hexdigest()[:24]
        compact = digest
    base = f"h{compact}"
    return (base[:63], f"{base}-svc"[:63], f"{base}-ing"[:63])


def base_labels_for_job(
    envelope: dict[str, Any],
    *,
    kueue_queue_name: str,
    user_id_label_value: str,
    job_id_label_value: str,
) -> dict[str, str]:
    workload = envelope["workload"]
    labels: dict[str, str] = {
        LABEL_MANAGED_BY: VALUE_MANAGED_BY_ORCHESTRATOR,
        LABEL_SUBMISSION_ID: envelope["submission_id"],
        LABEL_JOB_ID: job_id_label_value,
        LABEL_TENANT_ID: envelope["tenant_id"],
        LABEL_USER_ID: user_id_label_value,
        LABEL_WORKLOAD_KIND: str(workload["kind"]),
        KUEUE_LOCAL_QUEUE_LABEL: kueue_queue_name,
    }
    cid = envelope.get("campaign_id")
    if cid:
        labels[LABEL_CAMPAIGN_ID] = str(cid).strip()
    extra = workload.get("labels")
    if isinstance(extra, dict):
        for k, v in extra.items():
            if isinstance(k, str) and isinstance(v, str):
                labels[k] = v
    return labels
