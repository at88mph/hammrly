"""campaigns table and submission campaign linkage

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-30

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=256), nullable=False),
        sa.Column("user_id", sa.String(length=512), nullable=False),
        sa.Column("project_id", sa.String(length=256), nullable=True),
        sa.Column("name", sa.String(length=253), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="accepted"),
        sa.Column("item_count", sa.Integer(), nullable=True),
        sa.Column("counts_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("template_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_uri", sa.Text(), nullable=True),
        sa.Column("manifest_uri", sa.Text(), nullable=True),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column("cluster_id", sa.String(length=128), nullable=False, server_default="default"),
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
        sa.PrimaryKeyConstraint("campaign_id"),
    )
    op.create_index("ix_campaigns_tenant_id", "campaigns", ["tenant_id"])
    op.create_index("ix_campaigns_user_id", "campaigns", ["user_id"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    op.add_column("submissions", sa.Column("campaign_id", sa.String(length=36), nullable=True))
    op.add_column("submissions", sa.Column("item_key", sa.String(length=128), nullable=True))
    op.create_foreign_key(
        "fk_submissions_campaign_id",
        "submissions",
        "campaigns",
        ["campaign_id"],
        ["campaign_id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_submissions_campaign_id", "submissions", ["campaign_id"])
    op.create_index("ix_submissions_user_campaign", "submissions", ["user_id", "campaign_id"])
    op.create_index(
        "uq_submissions_campaign_item_key",
        "submissions",
        ["campaign_id", "item_key"],
        unique=True,
        postgresql_where=sa.text("campaign_id IS NOT NULL AND item_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_submissions_campaign_item_key", table_name="submissions")
    op.drop_index("ix_submissions_user_campaign", table_name="submissions")
    op.drop_index("ix_submissions_campaign_id", table_name="submissions")
    op.drop_constraint("fk_submissions_campaign_id", "submissions", type_="foreignkey")
    op.drop_column("submissions", "item_key")
    op.drop_column("submissions", "campaign_id")
    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_index("ix_campaigns_user_id", table_name="campaigns")
    op.drop_index("ix_campaigns_tenant_id", table_name="campaigns")
    op.drop_table("campaigns")
