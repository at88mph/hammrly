"""Watch indexed campaign pods and map completion index to submission rows."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from kubernetes import client, config
from kubernetes import watch
from kubernetes.client import V1Pod
from kubernetes.config import ConfigException

from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.k8s.labels import LABEL_CAMPAIGN_ID, LABEL_CAMPAIGN_JOBSET, VALUE_CAMPAIGN_JOBSET_INDEXED
from hammrly_orchestrator.persistence.repository import SubmissionRepository

logger = logging.getLogger(__name__)

_COMPLETION_INDEX_LABEL = "batch.kubernetes.io/job-completion-index"


def _configure_k8s(settings: Settings) -> None:
    try:
        config.load_incluster_config()
    except ConfigException:
        path = settings.k8s_kubeconfig_path
        if path:
            config.load_kube_config(config_file=path)
        else:
            config.load_kube_config()


def _completion_index_from_pod(pod: V1Pod) -> Optional[int]:
    labels = pod.metadata.labels or {} if pod.metadata else {}
    raw = labels.get(_COMPLETION_INDEX_LABEL)
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


def _map_pod_phase_to_status(pod: V1Pod) -> Optional[tuple[str, Optional[str]]]:
    phase = (pod.status.phase or "").strip() if pod.status else ""
    if phase == "Running":
        return "running", None
    if phase == "Succeeded":
        return "succeeded", None
    if phase == "Failed":
        reason = None
        if pod.status and pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                state = cs.state
                if state and state.terminated and state.terminated.reason:
                    reason = state.terminated.reason
                    break
        return "failed", reason
    return None


def _apply_pod(repository: SubmissionRepository, pod: V1Pod) -> None:
    labels = pod.metadata.labels or {} if pod.metadata else {}
    if labels.get(LABEL_CAMPAIGN_JOBSET) != VALUE_CAMPAIGN_JOBSET_INDEXED:
        return
    campaign_id = labels.get(LABEL_CAMPAIGN_ID)
    if not campaign_id:
        return
    idx = _completion_index_from_pod(pod)
    if idx is None:
        return
    mapped = _map_pod_phase_to_status(pod)
    if mapped is None:
        return
    new_status, detail = mapped
    repository.apply_campaign_indexed_pod_status(
        campaign_id=str(campaign_id),
        completion_index=idx,
        new_status=new_status,
        status_detail=detail,
    )


def run_campaign_pod_watch_loop(
    settings: Settings,
    repository: SubmissionRepository,
    stop_event: threading.Event,
) -> None:
    if not settings.campaign_indexed_pod_watch_enabled:
        return

    _configure_k8s(settings)
    core = client.CoreV1Api()
    ns = settings.pod_watch_namespace or settings.job_watch_namespace
    selector = f"{LABEL_CAMPAIGN_JOBSET}={VALUE_CAMPAIGN_JOBSET_INDEXED}"
    timeout = settings.pod_watch_timeout_seconds

    logger.info(
        "Campaign indexed pod watch starting namespace=%r label_selector=%r",
        ns,
        selector,
    )
    w = watch.Watch()
    while not stop_event.is_set():
        try:
            for event in w.stream(
                core.list_namespaced_pod,
                namespace=ns,
                label_selector=selector,
                timeout_seconds=timeout,
            ):
                if stop_event.is_set():
                    break
                etype = event["type"]
                obj = event["object"]
                if etype in ("ERROR", "BOOKMARK"):
                    continue
                if isinstance(obj, V1Pod):
                    _apply_pod(repository, obj)
        except Exception:
            logger.exception("Campaign pod watch failed; reconnecting")
        finally:
            try:
                w.stop()
            except Exception:
                pass
            w = watch.Watch()


def start_campaign_pod_watch_background(
    settings: Settings,
    repository: SubmissionRepository,
    stop_event: threading.Event,
) -> Optional[threading.Thread]:
    if not settings.pod_watch_enabled and not settings.job_watch_enabled:
        return None
    if not settings.campaign_indexed_pod_watch_enabled:
        return None

    t = threading.Thread(
        target=run_campaign_pod_watch_loop,
        name="campaign-pod-watch",
        args=(settings, repository, stop_event),
        daemon=True,
    )
    t.start()
    return t
