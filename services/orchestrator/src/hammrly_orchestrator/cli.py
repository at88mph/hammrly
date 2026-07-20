from __future__ import annotations

import logging
import sys
import threading
from typing import Any, Optional

import redis

from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.k8s import KubernetesSubmitter
from hammrly_orchestrator.k8s.drift_reconcile import start_drift_background
from hammrly_orchestrator.k8s.job_watch import start_job_watch_background
from hammrly_orchestrator.k8s.pod_watch import start_pod_watch_background
from hammrly_orchestrator.campaign.expander import CampaignExpander
from hammrly_orchestrator.campaign_listener import CampaignQueueListener
from hammrly_orchestrator.job_index import update_job_index_after_received
from hammrly_orchestrator.listener import JobQueueListener, install_signal_handlers
from hammrly_orchestrator.networking import normalize_workload_networking
from hammrly_orchestrator.persistence import SubmissionRepository, create_engine_from_url, create_session_factory

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    settings = Settings()

    engine = create_engine_from_url(settings.database_url)
    repository = SubmissionRepository(create_session_factory(engine))

    submitter: Optional[KubernetesSubmitter] = None
    if settings.k8s_submit_enabled:
        submitter = KubernetesSubmitter(settings)

    shutdown = threading.Event()

    index_redis = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_timeout=10,
        socket_connect_timeout=10,
    )

    start_job_watch_background(settings, repository, shutdown)
    start_pod_watch_background(settings, repository, shutdown)
    start_drift_background(settings, repository, shutdown)

    def on_envelope(envelope: dict[str, Any], message_id: str) -> None:
        submission_id = envelope.get("submission_id")
        job_id = envelope.get("job_id")
        user_id = envelope.get("user_id")
        kind = envelope.get("workload", {}).get("kind")
        logger.info(
            "Received job submission message_id=%s job_id=%s submission_id=%s user_id=%s kind=%s",
            message_id,
            job_id,
            submission_id,
            user_id,
            kind,
        )

        try:
            envelope["workload"] = normalize_workload_networking(envelope["workload"])
        except ValueError as e:
            logger.warning("Invalid networking for submission_id=%s: %s", submission_id, e)
            raise

        queue_name = settings.kueue_local_queue_for_workload_kind(str(kind))

        repository.record_received(
            envelope,
            queue_name=queue_name,
            cluster_id=settings.cluster_id,
            redis_message_id=message_id,
        )

        try:
            update_job_index_after_received(
                index_redis,
                settings,
                envelope,
                queue_name=queue_name,
            )
        except Exception:
            logger.warning(
                "job index update failed job_id=%s submission_id=%s",
                job_id,
                submission_id,
                exc_info=True,
            )

        if submitter is not None:
            if submission_id:
                repository.mark_building_spec(submission_id)
            try:
                job, access_desc = submitter.submit(envelope)
                if submission_id:
                    repository.mark_k8s_created(
                        submission_id,
                        job_name=job.metadata.name or "",
                        namespace=settings.k8s_namespace,
                        job_uid=job.metadata.uid or "",
                        resource_version=job.metadata.resource_version,
                        queue_name=queue_name,
                    )
                    if access_desc.public_url:
                        repository.update_submission_access_url(submission_id, access_desc.public_url)
            except Exception as e:
                if submission_id:
                    repository.mark_k8s_create_failed(submission_id, str(e))
                raise

    expander = CampaignExpander(settings, repository, submitter)

    def on_campaign(envelope: dict[str, Any], message_id: str) -> None:
        logger.info(
            "Received campaign message_id=%s campaign_id=%s user_id=%s",
            message_id,
            envelope.get("campaign_id"),
            envelope.get("user_id"),
        )
        expander.process(envelope, message_id)

    campaign_listener = CampaignQueueListener(
        settings,
        on_campaign=on_campaign,
        external_shutdown=shutdown,
    )

    campaign_thread = threading.Thread(
        target=campaign_listener.run_forever,
        name="campaign-listener-main",
        daemon=True,
    )
    campaign_thread.start()

    listener = JobQueueListener(
        settings,
        on_envelope=on_envelope,
        external_shutdown=shutdown,
    )
    install_signal_handlers(listener, shutdown)
    listener.run_forever()


if __name__ == "__main__":
    main()
