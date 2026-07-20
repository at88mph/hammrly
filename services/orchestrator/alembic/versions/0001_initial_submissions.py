"""initial submissions and submission_events

Revision ID: 0001
Revises:
Create Date: 2026-02-15

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=256), nullable=False),
        sa.Column("project_id", sa.String(length=256), nullable=True),
        sa.Column("user_id", sa.String(length=512), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="received",
        ),
        sa.Column("status_detail", sa.Text(), nullable=True),
        sa.Column("queue_name", sa.String(length=256), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("k8s_job_name", sa.String(length=253), nullable=True),
        sa.Column("k8s_namespace", sa.String(length=253), nullable=True),
        sa.Column("k8s_job_uid", sa.String(length=64), nullable=True),
        sa.Column("cluster_id", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("k8s_resource_version", sa.String(length=32), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("redis_stream_message_id", sa.String(length=128), nullable=True),
        sa.Column("payload_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("submission_id"),
    )
    op.create_index("ix_submissions_job_id", "submissions", ["job_id"], unique=True)
    op.create_index("ix_submissions_tenant_id", "submissions", ["tenant_id"])
    op.create_index("ix_submissions_user_id", "submissions", ["user_id"])
    op.create_index("ix_submissions_status", "submissions", ["status"])

    op.create_table(
        "submission_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["submissions.submission_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_submission_events_submission_id", "submission_events", ["submission_id"])


def downgrade() -> None:
    op.drop_index("ix_submission_events_submission_id", table_name="submission_events")
    op.drop_table("submission_events")
    op.drop_index("ix_submissions_status", table_name="submissions")
    op.drop_index("ix_submissions_user_id", table_name="submissions")
    op.drop_index("ix_submissions_tenant_id", table_name="submissions")
    op.drop_index("ix_submissions_job_id", table_name="submissions")
    op.drop_table("submissions")
