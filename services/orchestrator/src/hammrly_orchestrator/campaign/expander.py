from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from hammrly_orchestrator.campaign.manifest import load_campaign_items
from hammrly_orchestrator.campaign.merge import build_job_envelope
from hammrly_orchestrator.config import Settings
from hammrly_orchestrator.k8s.jobset_submitter import JobSetSubmitter
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
        jobset_submitter: Optional[JobSetSubmitter],
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._jobset_submitter = jobset_submitter

    def process(self, envelope: dict[str, Any], message_id: str) -> None:
        campaign_id = str(envelope["campaign_id"])
        self._repository.ensure_campaign(envelope, cluster_id=self._settings.cluster_id)

        if self._repository.campaign_has_jobset(campaign_id):
            logger.info("campaign_id=%s already has JobSet; skipping expand", campaign_id)
            return

        existing = self._repository.count_campaign_submissions(campaign_id)
        if existing > 0:
            logger.info(
                "campaign_id=%s resuming JobSet create (%s submissions, no JobSet yet)",
                campaign_id,
                existing,
            )
            self._resume_jobset(campaign_id, envelope)
            self._repository.finalize_campaign_expansion(campaign_id)
            return

        items = _resolve_items(envelope, self._settings)
        max_items = self._settings.campaign_max_items
        if len(items) > max_items:
            raise ValueError(f"campaign item count {len(items)} exceeds maximum {max_items}")

        self._repository.mark_campaign_expanding(campaign_id, item_count=len(items))
        self._expand_jobset(campaign_id, envelope, message_id, items)
        self._repository.finalize_campaign_expansion(campaign_id)

    def _resume_jobset(self, campaign_id: str, envelope: dict[str, Any]) -> None:
        entries = self._repository.list_campaign_manifest_entries(campaign_id)
        if not entries or self._jobset_submitter is None:
            return
        items = _resolve_items(envelope, self._settings)
        by_key = {str(it["item_key"]): it for it in items}
        manifest_entries: list[dict[str, Any]] = []
        for entry in entries:
            item = by_key.get(str(entry["item"]["item_key"]))
            if item is None:
                continue
            manifest_entries.append({**entry, "item": item})
        if not manifest_entries:
            return
        queue_name = self._settings.kueue_local_queue_for_workload_kind("headless")
        try:
            result = self._jobset_submitter.submit_campaign(envelope, manifest_entries=manifest_entries)
            self._repository.mark_campaign_jobset_created(
                campaign_id,
                jobset_name=result["jobset_name"],
                jobset_uid=result["jobset_uid"],
                configmap_name=result["configmap_name"],
                namespace=self._settings.k8s_namespace,
                resource_version=result.get("resource_version"),
                queue_name=queue_name,
                child_job_name=result["child_job_name"],
            )
        except Exception as e:
            logger.warning("campaign JobSet resume failed campaign_id=%s: %s", campaign_id, e)
            self._repository.mark_campaign_jobset_create_failed(campaign_id, str(e))

    def _expand_jobset(
        self,
        campaign_id: str,
        envelope: dict[str, Any],
        message_id: str,
        items: list[dict[str, Any]],
    ) -> None:
        queue_name = self._settings.kueue_local_queue_for_workload_kind("headless")
        manifest_entries: list[dict[str, Any]] = []

        for index, item in enumerate(items):
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
                completion_index=index,
            )
            self._repository.adjust_campaign_status_count(campaign_id, "received", 1)
            manifest_entries.append(
                {
                    "completion_index": index,
                    "item": item,
                    "submission_id": submission_id,
                    "job_id": job_id,
                }
            )

        if not manifest_entries or self._jobset_submitter is None:
            return

        try:
            result = self._jobset_submitter.submit_campaign(
                envelope,
                manifest_entries=manifest_entries,
            )
            self._repository.mark_campaign_jobset_created(
                campaign_id,
                jobset_name=result["jobset_name"],
                jobset_uid=result["jobset_uid"],
                configmap_name=result["configmap_name"],
                namespace=self._settings.k8s_namespace,
                resource_version=result.get("resource_version"),
                queue_name=queue_name,
                child_job_name=result["child_job_name"],
            )
        except Exception as e:
            logger.warning("campaign JobSet create failed campaign_id=%s: %s", campaign_id, e)
            self._repository.mark_campaign_jobset_create_failed(campaign_id, str(e))
