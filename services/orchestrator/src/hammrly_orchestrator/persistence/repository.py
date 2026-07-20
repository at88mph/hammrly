from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from hammrly_orchestrator.k8s.job_state import map_job_to_submission_status
from hammrly_orchestrator.k8s.labels import (
    LABEL_SUBMISSION_ID,
    normalize_job_id_label_value,
    normalize_user_id_label_value,
)
from hammrly_orchestrator.k8s.pod_spec import effective_gpu_count
from hammrly_orchestrator.persistence.models import Campaign, Submission, SubmissionEvent

logger = logging.getLogger(__name__)


def _parse_requested_at(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


class SubmissionRepository:
    """Persistence for submissions and lifecycle events (orchestrator writer)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session(self) -> Any:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _touch(now: datetime, row: Submission) -> None:
        row.updated_at = now

    @staticmethod
    def _add_event(
        session: Session,
        submission_id: str,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        session.add(
            SubmissionEvent(
                submission_id=submission_id,
                event_type=event_type,
                payload_json=payload,
            )
        )

    @staticmethod
    def _counts_get(counts: dict[str, Any], key: str) -> int:
        v = counts.get(key, 0)
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _counts_adjust(counts: dict[str, Any], key: str, delta: int) -> None:
        counts[key] = max(0, SubmissionRepository._counts_get(counts, key) + delta)

    def record_received(
        self,
        envelope: dict[str, Any],
        *,
        queue_name: str,
        cluster_id: str,
        redis_message_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        item_key: Optional[str] = None,
    ) -> None:
        workload = envelope["workload"]
        now = datetime.now(timezone.utc)
        project_id = envelope.get("project_id")
        if project_id is not None:
            project_id = str(project_id).strip() or None
        summary: dict[str, Any] = {
            "kind": workload.get("kind"),
            "name": workload.get("name"),
            "image": workload.get("image"),
            "gpu_count": effective_gpu_count(workload),
            "needs_ingress": bool(workload.get("needs_ingress")),
        }
        with self._session() as session:
            sid = envelope["submission_id"]
            row = session.get(Submission, sid)
            if row is None:
                row = Submission(
                    submission_id=sid,
                    job_id=str(envelope["job_id"]).strip(),
                    tenant_id=envelope["tenant_id"],
                    project_id=project_id,
                    user_id=envelope["user_id"],
                    status="received",
                    queue_name=queue_name,
                    priority=workload.get("priority"),
                    gpu_count=effective_gpu_count(workload),
                    cluster_id=cluster_id,
                    requested_at=_parse_requested_at(envelope.get("requested_at")),
                    redis_stream_message_id=redis_message_id,
                    payload_summary=summary,
                    campaign_id=campaign_id,
                    item_key=item_key,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                self._add_event(session, sid, "queued", {"redis_message_id": redis_message_id})
            else:
                row.redis_stream_message_id = redis_message_id or row.redis_stream_message_id
                row.gpu_count = effective_gpu_count(workload)
                self._touch(now, row)
                self._add_event(session, sid, "redelivered", {"redis_message_id": redis_message_id})

    def mark_building_spec(self, submission_id: str) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as session:
            row = session.get(Submission, submission_id)
            if row is None:
                logger.warning("mark_building_spec: unknown submission_id=%s", submission_id)
                return
            row.status = "building_spec"
            row.status_detail = None
            self._touch(now, row)
            self._add_event(session, submission_id, "building_spec", None)

    def mark_k8s_created(
        self,
        submission_id: str,
        *,
        job_name: str,
        namespace: str,
        job_uid: str,
        resource_version: Optional[str],
        queue_name: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as session:
            row = session.get(Submission, submission_id)
            if row is None:
                logger.warning("mark_k8s_created: unknown submission_id=%s", submission_id)
                return
            row.status = "submitted_to_cluster"
            row.status_detail = None
            row.k8s_job_name = job_name
            row.k8s_namespace = namespace
            row.k8s_job_uid = job_uid
            row.k8s_resource_version = resource_version
            row.queue_name = queue_name
            self._touch(now, row)
            self._add_event(
                session,
                submission_id,
                "k8s_create_ok",
                {"job_name": job_name, "namespace": namespace, "uid": job_uid, "rv": resource_version},
            )

    def update_submission_access_url(self, submission_id: str, url: Optional[str]) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as session:
            row = session.get(Submission, submission_id)
            if row is None:
                logger.warning("update_submission_access_url: unknown submission_id=%s", submission_id)
                return
            row.access_url = url
            self._touch(now, row)
            self._add_event(session, submission_id, "access_url_set", {"access_url": url})

    def apply_job_watch_update(
        self,
        job: Any,
        *,
        deleted: bool = False,
        label_job_id: Optional[str] = None,
        label_user_id: Optional[str] = None,
    ) -> None:
        """Persist status from a Job watch event. `job` is V1Job."""
        from kubernetes.client import V1Job

        if not isinstance(job, V1Job):
            return
        meta = job.metadata
        if not meta or not meta.labels:
            return
        sid = meta.labels.get(LABEL_SUBMISSION_ID)
        if not sid:
            return
        rv = meta.resource_version
        now = datetime.now(timezone.utc)

        if deleted:
            new_status = "unknown"
            detail = "Job object deleted in cluster"
        else:
            new_status, detail = map_job_to_submission_status(job)

        with self._session() as session:
            row = session.get(Submission, sid)
            if row is None:
                logger.debug("watch update for unknown submission_id=%s (skipped)", sid)
                return

            if label_job_id:
                expected_j = normalize_job_id_label_value(row.job_id)
                if label_job_id not in (expected_j, str(row.job_id).strip()):
                    logger.warning(
                        "job_id label mismatch submission_id=%s db=%s label=%s",
                        sid,
                        row.job_id,
                        label_job_id,
                    )
            if label_user_id:
                expected_u = normalize_user_id_label_value(row.user_id)
                if label_user_id not in (expected_u, str(row.user_id).strip()):
                    logger.warning(
                        "user_id label mismatch submission_id=%s db=%s label=%s",
                        sid,
                        row.user_id,
                        label_user_id,
                    )

            if (
                not deleted
                and str(rv or "") == str(row.k8s_resource_version or "")
                and row.status == new_status
                and (detail or None) == (row.status_detail or None)
            ):
                return

            if row.status == "ready" and new_status == "running" and not deleted:
                return

            old_status = row.status
            row.status = new_status
            row.status_detail = detail
            if rv:
                row.k8s_resource_version = str(rv)
            self._touch(now, row)
            evt = "job_deleted" if deleted else f"watch_{new_status}"
            self._add_event(
                session,
                sid,
                evt,
                {
                    "resource_version": rv,
                    "label_job_id": label_job_id,
                },
            )
            if row.campaign_id and old_status != new_status:
                self._rollup_submission_status_in_session(
                    session,
                    row.campaign_id,
                    old_status=old_status,
                    new_status=new_status,
                )

    def mark_cluster_job_missing(self, submission_id: str, reason: str) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as session:
            row = session.get(Submission, submission_id)
            if row is None:
                return

            if row.status in ("succeeded", "failed", "unknown"):
                return

            row.status = "unknown"
            row.status_detail = reason[:2000]
            self._touch(now, row)
            self._add_event(session, submission_id, "cluster_job_missing", {"reason": reason})

    def mark_session_ready(self, submission_id: str) -> None:
        """Mark an ingress-backed interactive session ready to open (idempotent)."""
        now = datetime.now(timezone.utc)
        with self._session() as session:
            row = session.get(Submission, submission_id)
            if row is None:
                logger.warning("mark_session_ready: unknown submission_id=%s", submission_id)
                return

            summary = row.payload_summary if isinstance(row.payload_summary, dict) else {}
            if not summary.get("needs_ingress"):
                logger.debug(
                    "mark_session_ready skipped submission_id=%s (needs_ingress=false)",
                    submission_id,
                )
                return

            if row.status == "ready":
                return

            if row.status not in ("running", "admitted"):
                logger.debug(
                    "mark_session_ready skipped submission_id=%s status=%s",
                    submission_id,
                    row.status,
                )
                return

            row.status = "ready"
            row.status_detail = None
            self._touch(now, row)
            self._add_event(
                session,
                submission_id,
                "session_ready",
                {"access_url": row.access_url},
            )

    def list_active_submission_ids(self, statuses: tuple[str, ...]) -> list[str]:
        with self._session() as session:
            stmt = select(Submission.submission_id).where(Submission.status.in_(statuses))
            return list(session.scalars(stmt).all())

    def _rollup_submission_status_in_session(
        self,
        session: Session,
        campaign_id: str,
        *,
        old_status: str,
        new_status: str,
    ) -> None:
        camp = session.get(Campaign, campaign_id)
        if camp is None:
            return
        counts = dict(camp.counts_json or {})
        self._counts_adjust(counts, old_status, -1)
        self._counts_adjust(counts, new_status, 1)
        camp.counts_json = counts
        self._touch(datetime.now(timezone.utc), camp)

    def ensure_campaign(self, envelope: dict[str, Any], *, cluster_id: str) -> None:
        campaign_id = str(envelope["campaign_id"])
        camp_meta = envelope.get("campaign") or {}
        template = envelope["template"]
        now = datetime.now(timezone.utc)
        project_id = envelope.get("project_id")
        if project_id is not None:
            project_id = str(project_id).strip() or None
        summary = {
            "kind": template.get("kind"),
            "name": template.get("name"),
            "image": template.get("image"),
            "gpu_count": effective_gpu_count(template),
        }
        with self._session() as session:
            row = session.get(Campaign, campaign_id)
            if row is not None:
                return
            row = Campaign(
                campaign_id=campaign_id,
                tenant_id=envelope["tenant_id"],
                user_id=envelope["user_id"],
                project_id=project_id,
                name=str(camp_meta.get("name") or "campaign"),
                description=camp_meta.get("description"),
                status="accepted",
                item_count=envelope.get("item_count"),
                counts_json={},
                template_summary=summary,
                output_uri=camp_meta.get("output_uri"),
                manifest_uri=envelope.get("manifest_uri"),
                manifest_sha256=envelope.get("manifest_sha256"),
                cluster_id=cluster_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)

    def mark_campaign_expanding(self, campaign_id: str, *, item_count: int) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as session:
            row = session.get(Campaign, campaign_id)
            if row is None:
                return
            row.status = "expanding"
            row.item_count = item_count
            self._touch(now, row)

    def count_campaign_submissions(self, campaign_id: str) -> int:
        with self._session() as session:
            stmt = select(Submission.submission_id).where(Submission.campaign_id == campaign_id)
            return len(list(session.scalars(stmt).all()))

    def submission_exists_for_campaign_item(self, campaign_id: str, item_key: str) -> bool:
        with self._session() as session:
            stmt = select(Submission.submission_id).where(
                Submission.campaign_id == campaign_id,
                Submission.item_key == item_key,
            )
            return session.scalar(stmt) is not None

    def adjust_campaign_status_count(self, campaign_id: str, status: str, delta: int) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as session:
            row = session.get(Campaign, campaign_id)
            if row is None:
                return
            counts = dict(row.counts_json or {})
            self._counts_adjust(counts, status, delta)
            row.counts_json = counts
            if row.status == "accepted":
                row.status = "active"
            self._touch(now, row)

    def transition_campaign_submission_status(
        self,
        campaign_id: str,
        submission_id: str,
        *,
        old_status: str,
        new_status: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as session:
            sub = session.get(Submission, submission_id)
            if sub is None or sub.campaign_id != campaign_id:
                return
            if sub.status != new_status:
                sub.status = new_status
                self._touch(now, sub)
            self._rollup_submission_status_in_session(
                session, campaign_id, old_status=old_status, new_status=new_status
            )

    def record_campaign_item_failed(self, campaign_id: str, *, item_key: str, detail: str) -> None:
        self.adjust_campaign_status_count(campaign_id, "failed", 1)

    def finalize_campaign_expansion(self, campaign_id: str) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as session:
            row = session.get(Campaign, campaign_id)
            if row is None:
                return
            counts = row.counts_json or {}
            failed = self._counts_get(counts, "failed")
            item_count = row.item_count or 0
            if item_count and failed >= item_count:
                row.status = "failed"
            elif failed > 0:
                row.status = "partial_failed"
            else:
                row.status = "completed"
            self._touch(now, row)

    def mark_k8s_create_failed(self, submission_id: str, detail: str) -> None:
        now = datetime.now(timezone.utc)
        with self._session() as session:
            row = session.get(Submission, submission_id)
            if row is None:
                logger.warning("mark_k8s_create_failed: unknown submission_id=%s", submission_id)
                return
            old_status = row.status
            row.status = "failed"
            row.status_detail = detail[:2000]
            self._touch(now, row)
            self._add_event(session, submission_id, "k8s_create_err", {"error": detail[:4000]})
            if row.campaign_id and old_status != "failed":
                self._rollup_submission_status_in_session(
                    session, row.campaign_id, old_status=old_status, new_status="failed"
                )
