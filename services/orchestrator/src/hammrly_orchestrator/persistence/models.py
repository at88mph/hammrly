from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaigns"

    campaign_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    name: Mapped[str] = mapped_column(String(253), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="accepted")
    item_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    counts_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    template_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    output_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manifest_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manifest_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cluster_id: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Submission(Base):
    __tablename__ = "submissions"

    submission_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    user_id: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="received")
    status_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    queue_name: Mapped[str] = mapped_column(String(256), nullable=False)
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gpu_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    k8s_job_name: Mapped[Optional[str]] = mapped_column(String(253), nullable=True)
    k8s_namespace: Mapped[Optional[str]] = mapped_column(String(253), nullable=True)
    k8s_job_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cluster_id: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    k8s_resource_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    access_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    redis_stream_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payload_summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    campaign_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("campaigns.campaign_id", ondelete="SET NULL"), index=True, nullable=True
    )
    item_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    events: Mapped[list["SubmissionEvent"]] = relationship(
        "SubmissionEvent",
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class SubmissionEvent(Base):
    __tablename__ = "submission_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("submissions.submission_id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    submission: Mapped["Submission"] = relationship("Submission", back_populates="events")
