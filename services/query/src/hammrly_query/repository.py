from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import Session

from hammrly_query.config import Settings
from hammrly_query.jwt_auth import Principal
from hammrly_query.models import Campaign, Submission, SubmissionEvent, UserNotification


def _scope_campaigns(stmt: Select[tuple[Campaign]], principal: Principal, settings: Settings) -> Select:
    stmt = stmt.where(Campaign.user_id == principal.user_id)
    if principal.tenant_from_token:
        stmt = stmt.where(Campaign.tenant_id == principal.tenant_from_token)
    if settings.cluster_id:
        stmt = stmt.where(Campaign.cluster_id == settings.cluster_id)
    return stmt


def _scope_submissions(stmt: Select[tuple[Submission]], principal: Principal, settings: Settings) -> Select:
    stmt = stmt.where(Submission.user_id == principal.user_id)
    if principal.tenant_from_token:
        stmt = stmt.where(Submission.tenant_id == principal.tenant_from_token)
    if settings.cluster_id:
        stmt = stmt.where(Submission.cluster_id == settings.cluster_id)
    return stmt


def get_submission_by_job_id(
    session: Session,
    settings: Settings,
    principal: Principal,
    job_id: str,
) -> Optional[Submission]:
    stmt = select(Submission).where(Submission.job_id == job_id)
    stmt = _scope_submissions(stmt, principal, settings)
    return session.scalar(stmt)


def list_submission_events(session: Session, submission_id: str) -> list[SubmissionEvent]:
    return list(
        session.scalars(
            select(SubmissionEvent)
            .where(SubmissionEvent.submission_id == submission_id)
            .order_by(SubmissionEvent.occurred_at.asc())
        ).all()
    )


def list_interactive_submissions(
    session: Session,
    settings: Settings,
    principal: Principal,
    *,
    limit: int,
    offset: int,
) -> list[Submission]:
    kinds = settings.interactive_kinds_list
    if not kinds:
        return []
    kind_expr = Submission.payload_summary["kind"].as_string()
    stmt = select(Submission).where(
        kind_expr.in_(kinds),
        Submission.payload_summary.isnot(None),
    )
    stmt = _scope_submissions(stmt, principal, settings)
    stmt = stmt.order_by(Submission.updated_at.desc()).limit(limit).offset(offset)
    return list(session.scalars(stmt).all())


def get_campaign_by_id(
    session: Session,
    settings: Settings,
    principal: Principal,
    campaign_id: str,
) -> Optional[Campaign]:
    stmt = select(Campaign).where(Campaign.campaign_id == campaign_id)
    stmt = _scope_campaigns(stmt, principal, settings)
    return session.scalar(stmt)


def counts_int(counts: dict[str, Any], key: str) -> int:
    try:
        return int(counts.get(key, 0))
    except (TypeError, ValueError):
        return 0


def list_campaign_failed_sample(
    session: Session,
    settings: Settings,
    principal: Principal,
    campaign_id: str,
    *,
    limit: int = 10,
) -> list[Submission]:
    stmt = select(Submission).where(
        Submission.campaign_id == campaign_id,
        Submission.status == "failed",
    )
    stmt = _scope_submissions(stmt, principal, settings)
    stmt = stmt.order_by(Submission.updated_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def list_campaign_jobs(
    session: Session,
    settings: Settings,
    principal: Principal,
    campaign_id: str,
    *,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Submission]:
    stmt = select(Submission).where(Submission.campaign_id == campaign_id)
    if status:
        stmt = stmt.where(Submission.status == status)
    stmt = _scope_submissions(stmt, principal, settings)
    stmt = stmt.order_by(Submission.updated_at.desc()).limit(limit).offset(offset)
    return list(session.scalars(stmt).all())


def _scope_notifications(
    stmt: Select[tuple[UserNotification]],
    principal: Principal,
) -> Select[tuple[UserNotification]]:
    stmt = stmt.where(UserNotification.user_id == principal.user_id)
    if principal.tenant_from_token:
        stmt = stmt.where(UserNotification.tenant_id == principal.tenant_from_token)
    return stmt


def list_notifications(
    session: Session,
    principal: Principal,
    *,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[UserNotification]:
    stmt = select(UserNotification)
    stmt = _scope_notifications(stmt, principal)
    if unread_only:
        stmt = stmt.where(UserNotification.read_at.is_(None))
    stmt = stmt.order_by(UserNotification.created_at.desc()).limit(limit).offset(offset)
    return list(session.scalars(stmt).all())


def count_unread_notifications(session: Session, principal: Principal) -> int:
    stmt = select(func.count()).select_from(UserNotification).where(
        UserNotification.user_id == principal.user_id,
        UserNotification.read_at.is_(None),
    )
    if principal.tenant_from_token:
        stmt = stmt.where(UserNotification.tenant_id == principal.tenant_from_token)
    return int(session.scalar(stmt) or 0)


def get_notification(
    session: Session,
    principal: Principal,
    notification_id: int,
) -> Optional[UserNotification]:
    stmt = select(UserNotification).where(UserNotification.id == notification_id)
    stmt = _scope_notifications(stmt, principal)
    return session.scalar(stmt)


def mark_notification_read(
    session: Session,
    principal: Principal,
    notification_id: int,
) -> Optional[UserNotification]:
    row = get_notification(session, principal, notification_id)
    if row is None:
        return None
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def mark_all_notifications_read(session: Session, principal: Principal) -> int:
    now = datetime.now(timezone.utc)
    stmt = (
        update(UserNotification)
        .where(
            UserNotification.user_id == principal.user_id,
            UserNotification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    if principal.tenant_from_token:
        stmt = stmt.where(UserNotification.tenant_id == principal.tenant_from_token)
    result = session.execute(stmt)
    session.commit()
    return int(result.rowcount or 0)


def latest_notification_id(session: Session, principal: Principal) -> Optional[int]:
    stmt = select(UserNotification.id)
    stmt = _scope_notifications(stmt, principal)
    stmt = stmt.order_by(UserNotification.id.desc()).limit(1)
    return session.scalar(stmt)
