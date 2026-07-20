"""submissions gpu_count

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-15

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("gpu_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("submissions", "gpu_count")
