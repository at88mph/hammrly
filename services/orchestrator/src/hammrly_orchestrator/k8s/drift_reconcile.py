from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Set

from kubernetes import client, config
from kubernetes.config import ConfigException

from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.k8s.labels import LABEL_SUBMISSION_ID
from hammrly_orchestrator.persistence.repository import SubmissionRepository

logger = logging.getLogger(__name__)

_ACTIVE_DRIFT_STATUSES = (
    "received",
    "building_spec",
    "submitted_to_cluster",
    "admitted",
    "running",
)


def _configure_k8s(settings: Settings) -> None:
    try:
        config.load_incluster_config()
    except ConfigException:
        path = settings.k8s_kubeconfig_path
        if path:
            config.load_kube_config(config_file=path)
        else:
            config.load_kube_config()


def run_drift_reconcile_once(
    settings: Settings,
    repository: SubmissionRepository,
) -> None:
    """LIST Jobs; mark DB rows unknown if a terminal-ish row no longer has a cluster Job."""
    _configure_k8s(settings)
    batch = client.BatchV1Api()
    custom = client.CustomObjectsApi()
    ns = settings.job_watch_namespace
    selector = settings.job_watch_label_selector

    try:
        resp = batch.list_namespaced_job(namespace=ns, label_selector=selector)
    except Exception:
        logger.exception("drift: list_namespaced_job failed")
        return

    in_cluster: Set[str] = set()
    for job in resp.items or []:
        meta = job.metadata
        if not meta or not meta.labels:
            continue
        if meta.labels.get("hammrly.io/campaign-jobset") == "indexed":
            continue
        sid = meta.labels.get(LABEL_SUBMISSION_ID)
        if sid:
            in_cluster.add(sid)

    jobset_campaigns: Set[str] = set()
    try:
        js_resp = custom.list_namespaced_custom_object(
            group=settings.jobset_api_group,
            version=settings.jobset_api_version,
            namespace=ns,
            plural=settings.jobset_plural,
            label_selector=settings.job_watch_label_selector,
        )
        for item in js_resp.get("items") or []:
            meta = item.get("metadata") or {}
            labels = meta.get("labels") or {}
            cid = labels.get("hammrly.io/campaign-id")
            if cid:
                jobset_campaigns.add(str(cid))
    except Exception:
        logger.exception("drift: list JobSet failed")

    active_ids = repository.list_active_submission_ids(_ACTIVE_DRIFT_STATUSES)
    for sid in active_ids:
        camp_id = repository.campaign_id_for_submission(sid)
        if camp_id and camp_id in jobset_campaigns:
            continue
        if sid not in in_cluster:
            repository.mark_cluster_job_missing(
                sid,
                reason="Job not found in cluster during drift reconcile LIST",
            )


def drift_loop(
    settings: Settings,
    repository: SubmissionRepository,
    stop_event: threading.Event,
) -> None:
    interval = settings.job_drift_reconcile_interval_sec
    if interval <= 0:
        return
    while not stop_event.is_set():
        if stop_event.wait(timeout=interval):
            break
        run_drift_reconcile_once(settings, repository)


def start_drift_background(
    settings: Settings,
    repository: SubmissionRepository,
    stop_event: threading.Event,
) -> Optional[threading.Thread]:
    if not settings.job_watch_enabled:
        return None
    if settings.job_drift_reconcile_interval_sec <= 0:
        return None
    t = threading.Thread(
        target=drift_loop,
        name="job-drift",
        args=(settings, repository, stop_event),
        daemon=True,
    )
    t.start()
    return t
