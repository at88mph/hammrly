from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from hammrly_orchestrator.campaign.manifest import load_campaign_items
from hammrly_orchestrator.campaign.merge import build_job_envelope
from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.k8s import KubernetesSubmitter
from hammrly_orchestrator.networking import normalize_workload_networking
from hammrly_orchestrator.persistence.repository import SubmissionRepository

logger = logging.getLogger(__name__)


def _resolve_items(envelope: dict[str, Any], settings: Settings) -> list[dict[str, Any]]:
    inline = envelope.get("items")
    if isinstance(inline, list):
        return inline
    manifest_uri = envelope.get("manifest_uri")
    if not manifest_uri:
        raise ValueError("campaign envelope requires items or manifest_uri")
    return load_campaign_items(
        str(manifest_uri),
        expected_sha256=envelope.get("manifest_sha256"),
    )


class CampaignExpander:
    def __init__(
        self,
        settings: Settings,
        repository: SubmissionRepository,
        submitter: Optional[KubernetesSubmitter],
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._submitter = submitter

    def process(self, envelope: dict[str, Any], message_id: str) -> None:
        campaign_id = str(envelope["campaign_id"])
        self._repository.ensure_campaign(envelope, cluster_id=self._settings.cluster_id)

        existing = self._repository.count_campaign_submissions(campaign_id)
        if existing > 0:
            logger.info("campaign_id=%s already has %s submissions; skipping expand", campaign_id, existing)
            return

        items = _resolve_items(envelope, self._settings)
        max_items = self._settings.campaign_max_items
        if len(items) > max_items:
            raise ValueError(f"campaign item count {len(items)} exceeds maximum {max_items}")

        self._repository.mark_campaign_expanding(campaign_id, item_count=len(items))

        queue_name = self._settings.kueue_local_queue_for_workload_kind("headless")
        chunk = self._settings.campaign_expand_chunk_size
        min_interval = 1.0 / self._settings.campaign_expand_rps if self._settings.campaign_expand_rps > 0 else 0.0
        last_create = 0.0

        for i in range(0, len(items), chunk):
            batch = items[i : i + chunk]
            for item in batch:
                item_key = str(item["item_key"])
                if self._repository.submission_exists_for_campaign_item(campaign_id, item_key):
                    continue

                submission_id = str(uuid.uuid4())
                job_id = str(uuid.uuid4())
                job_env = build_job_envelope(
                    envelope,
                    item,
                    submission_id=submission_id,
                    job_id=job_id,
                )
                try:
                    job_env["workload"] = normalize_workload_networking(job_env["workload"])
                except ValueError as e:
                    self._repository.record_campaign_item_failed(
                        campaign_id,
                        item_key=item_key,
                        detail=str(e),
                    )
                    continue

                self._repository.record_received(
                    job_env,
                    queue_name=queue_name,
                    cluster_id=self._settings.cluster_id,
                    redis_message_id=message_id,
                    campaign_id=campaign_id,
                    item_key=item_key,
                )
                self._repository.adjust_campaign_status_count(campaign_id, "received", 1)

                if self._submitter is None:
                    continue

                if min_interval > 0:
                    elapsed = time.monotonic() - last_create
                    if elapsed < min_interval:
                        time.sleep(min_interval - elapsed)

                self._repository.mark_building_spec(submission_id)
                try:
                    job, access_desc = self._submitter.submit(job_env)
                    last_create = time.monotonic()
                    self._repository.mark_k8s_created(
                        submission_id,
                        job_name=job.metadata.name or "",
                        namespace=self._settings.k8s_namespace,
                        job_uid=job.metadata.uid or "",
                        resource_version=job.metadata.resource_version,
                        queue_name=queue_name,
                    )
                    if access_desc.public_url:
                        self._repository.update_submission_access_url(
                            submission_id, access_desc.public_url
                        )
                    self._repository.transition_campaign_submission_status(
                        campaign_id,
                        submission_id,
                        old_status="received",
                        new_status="submitted_to_cluster",
                    )
                except Exception as e:
                    logger.warning(
                        "campaign item k8s create failed campaign_id=%s item_key=%s: %s",
                        campaign_id,
                        item_key,
                        e,
                    )
                    self._repository.mark_k8s_create_failed(submission_id, str(e))

        self._repository.finalize_campaign_expansion(campaign_id)
