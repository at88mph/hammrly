"""Extract structured workload error manifests from Job annotations or pod logs."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from kubernetes.client import CoreV1Api, V1Job

logger = logging.getLogger(__name__)

ANNOTATION_WORKLOAD_ERROR = "hammrly.io/workload-error"
LOG_MARKER = "HAMMRLY_WORKLOAD_ERROR="
_OUTPUT_WATCHER_CONTAINER = "output-watcher"


def status_detail_from_error(err: dict[str, Any]) -> str:
    code = str(err.get("code") or "error").strip() or "error"
    message = str(err.get("message") or "").strip()
    if message:
        return f"{code}: {message}"[:2000]
    return code[:2000]


def compact_error_payload(err: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("schema_version", "status", "code", "message", "finished_at"):
        if key in err and err[key] is not None:
            out[key] = err[key]
    details = err.get("details")
    if details is not None:
        raw = json.dumps(details, default=str)
        if len(raw) > 2000:
            out["details"] = {"_truncated": True, "preview": raw[:500]}
        else:
            out["details"] = details
    return out


def parse_error_json(raw: str) -> Optional[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    # Sidecar log line shape: {"status":"error","payload":{...}}
    if data.get("status") == "error" and isinstance(data.get("payload"), dict):
        payload = data["payload"]
        if payload.get("status") == "error" or payload.get("code") or payload.get("message"):
            return payload
    if data.get("status") == "error" or data.get("code") or data.get("message"):
        return data
    return None


def workload_error_from_job_annotations(job: V1Job) -> Optional[dict[str, Any]]:
    meta = job.metadata
    if not meta or not meta.annotations:
        return None
    raw = meta.annotations.get(ANNOTATION_WORKLOAD_ERROR)
    if not raw:
        return None
    return parse_error_json(raw)


_MARKER_RE = re.compile(re.escape(LOG_MARKER) + r"(\{.*\})\s*$")


def parse_workload_error_from_log_text(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    # Prefer explicit marker lines (newest last).
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        if line.startswith(LOG_MARKER):
            err = parse_error_json(line[len(LOG_MARKER) :])
            if err:
                return err
        m = _MARKER_RE.search(line)
        if m:
            err = parse_error_json(m.group(1))
            if err:
                return err
        if '"status"' in line and ("error" in line):
            err = parse_error_json(line)
            if err:
                return err
    return None


def workload_error_from_pod_logs(
    core: CoreV1Api,
    *,
    namespace: str,
    job: V1Job,
) -> Optional[dict[str, Any]]:
    meta = job.metadata
    if not meta or not meta.name:
        return None
    job_name = meta.name
    try:
        pods = core.list_namespaced_pod(
            namespace=namespace,
            label_selector=f"job-name={job_name}",
        )
    except Exception:
        logger.debug("list pods for job=%s failed", job_name, exc_info=True)
        return None

    items = list(pods.items or [])
    # Prefer most recently created pod.
    items.sort(
        key=lambda p: getattr(getattr(p, "metadata", None), "creation_timestamp", None) or 0,
        reverse=True,
    )
    for pod in items:
        pname = getattr(getattr(pod, "metadata", None), "name", None)
        if not pname:
            continue
        try:
            log_text = core.read_namespaced_pod_log(
                name=pname,
                namespace=namespace,
                container=_OUTPUT_WATCHER_CONTAINER,
                tail_lines=200,
            )
        except Exception:
            try:
                log_text = core.read_namespaced_pod_log(
                    name=pname,
                    namespace=namespace,
                    tail_lines=200,
                )
            except Exception:
                logger.debug("read logs for pod=%s failed", pname, exc_info=True)
                continue
        err = parse_workload_error_from_log_text(str(log_text or ""))
        if err:
            return err
    return None


def resolve_workload_error(
    job: V1Job,
    *,
    core: Optional[CoreV1Api] = None,
    namespace: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    err = workload_error_from_job_annotations(job)
    if err:
        return err
    if core is not None and namespace:
        return workload_error_from_pod_logs(core, namespace=namespace, job=job)
    return None
