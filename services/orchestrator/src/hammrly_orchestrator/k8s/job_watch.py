from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from kubernetes import client, config
from kubernetes import watch
from kubernetes.client import V1Job
from kubernetes.config import ConfigException

from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.k8s.job_state import job_id_from_job, user_id_from_job
from hammrly_orchestrator.k8s.labels import LABEL_JOB_ID, LABEL_SUBMISSION_ID, LABEL_USER_ID
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


def sync_jobs_once(
    *,
    batch: client.BatchV1Api,
    namespace: str,
    label_selector: str,
    repository: SubmissionRepository,
) -> None:
    """LIST all matching Jobs and reconcile DB (startup / drift helper)."""
    try:
        resp = batch.list_namespaced_job(namespace=namespace, label_selector=label_selector)
    except Exception:
        logger.exception("list_namespaced_job failed during sync")
        return
    for job in resp.items or []:
        if not isinstance(job, V1Job):
            continue
        repository.apply_job_watch_update(
            job,
            deleted=False,
            label_job_id=job_id_from_job(job),
            label_user_id=user_id_from_job(job),
        )


def run_job_watch_loop(
    settings: Settings,
    repository: SubmissionRepository,
    stop_event: threading.Event,
) -> None:
    """Blocking watch loop (intended for a background thread)."""
    _configure_k8s(settings)
    batch = client.BatchV1Api()
    ns = settings.job_watch_namespace
    selector = settings.job_watch_label_selector
    timeout = settings.job_watch_timeout_seconds

    logger.info(
        "Job watch starting namespace=%r label_selector=%r",
        ns,
        selector,
    )
    sync_jobs_once(batch=batch, namespace=ns, label_selector=selector, repository=repository)

    w = watch.Watch()
    while not stop_event.is_set():
        try:
            for event in w.stream(
                batch.list_namespaced_job,
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
                    logger.warning("watch ERROR event: %s", event)
                    break

                if not isinstance(obj, V1Job):
                    continue

                if etype == "DELETED":
                    labels = obj.metadata.labels or {}
                    sid = labels.get(LABEL_SUBMISSION_ID)
                    if sid:
                        repository.apply_job_watch_update(
                            obj,
                            deleted=True,
                            label_job_id=labels.get(LABEL_JOB_ID),
                            label_user_id=labels.get(LABEL_USER_ID),
                        )
                    continue

                repository.apply_job_watch_update(
                    obj,
                    deleted=False,
                    label_job_id=job_id_from_job(obj),
                    label_user_id=user_id_from_job(obj),
                )
        except Exception:
            logger.exception("Job watch stream failed; reconnecting after backoff")
            time.sleep(3)
        finally:
            try:
                w.stop()
            except Exception:
                pass
            w = watch.Watch()

    logger.info("Job watch stopped")


def start_job_watch_background(
    settings: Settings,
    repository: SubmissionRepository,
    stop_event: threading.Event,
) -> Optional[threading.Thread]:
    if not settings.job_watch_enabled:
        return None

    t = threading.Thread(
        target=run_job_watch_loop,
        name="job-watch",
        args=(settings, repository, stop_event),
        daemon=True,
    )
    t.start()
    return t
