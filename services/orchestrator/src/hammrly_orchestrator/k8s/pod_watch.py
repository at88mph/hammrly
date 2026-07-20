"""Background Pod watch: mark ingress-backed sessions ready when probes succeed.

Watches pods labeled for orchestrator-managed workloads; when a pod's Ready
condition becomes True (readinessProbe passed), calls
``SubmissionRepository.mark_session_ready`` so Query clients can poll until
``status == "ready"`` and open ``access_url``.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from kubernetes import client, config
from kubernetes import watch
from kubernetes.client import V1Pod
from kubernetes.config import ConfigException

from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.k8s.labels import LABEL_SUBMISSION_ID
from hammrly_orchestrator.persistence.repository import SubmissionRepository

logger = logging.getLogger(__name__)


def _configure_k8s(settings: Settings) -> None:
    try:
        config.load_incluster_config()
    except ConfigException:
        path = settings.k8s_kubeconfig_path
        if path:
            config.load_kube_config(config_file=path)
        else:
            config.load_kube_config()


def _pod_is_ready(pod: V1Pod) -> bool:
    status = pod.status
    if not status:
        return False
    for cond in status.conditions or []:
        if getattr(cond, "type", None) == "Ready" and getattr(cond, "status", None) == "True":
            return True
    return False


def sync_pods_once(
    *,
    core: client.CoreV1Api,
    namespace: str,
    label_selector: str,
    repository: SubmissionRepository,
) -> None:
    try:
        resp = core.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
    except Exception:
        logger.exception("list_namespaced_pod failed during pod sync")
        return
    for pod in resp.items or []:
        if not isinstance(pod, V1Pod):
            continue
        if not _pod_is_ready(pod):
            continue
        labels = pod.metadata.labels or {} if pod.metadata else {}
        sid = labels.get(LABEL_SUBMISSION_ID)
        if sid:
            repository.mark_session_ready(sid)


def run_pod_watch_loop(
    settings: Settings,
    repository: SubmissionRepository,
    stop_event: threading.Event,
) -> None:
    """Blocking pod watch loop (intended for a background thread)."""
    _configure_k8s(settings)
    core = client.CoreV1Api()
    ns = settings.pod_watch_namespace
    selector = settings.pod_watch_label_selector
    timeout = settings.pod_watch_timeout_seconds

    logger.info(
        "Pod watch starting namespace=%r label_selector=%r",
        ns,
        selector,
    )
    sync_pods_once(core=core, namespace=ns, label_selector=selector, repository=repository)

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
                if etype == "BOOKMARK":
                    continue
                if etype == "ERROR":
                    logger.warning("pod watch ERROR event: %s", event)
                    break

                if not isinstance(obj, V1Pod):
                    continue
                if etype == "DELETED":
                    continue
                if not _pod_is_ready(obj):
                    continue

                labels = obj.metadata.labels or {} if obj.metadata else {}
                sid = labels.get(LABEL_SUBMISSION_ID)
                if sid:
                    repository.mark_session_ready(sid)
        except Exception:
            logger.exception("Pod watch stream failed; reconnecting after backoff")
            time.sleep(3)
        finally:
            try:
                w.stop()
            except Exception:
                pass
            w = watch.Watch()

    logger.info("Pod watch stopped")


def start_pod_watch_background(
    settings: Settings,
    repository: SubmissionRepository,
    stop_event: threading.Event,
) -> Optional[threading.Thread]:
    if not settings.pod_watch_enabled:
        return None

    t = threading.Thread(
        target=run_pod_watch_loop,
        name="pod-watch",
        args=(settings, repository, stop_event),
        daemon=True,
    )
    t.start()
    return t
