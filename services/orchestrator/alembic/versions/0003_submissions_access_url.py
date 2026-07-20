"""submissions access_url

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-15

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("access_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("submissions", "access_url")
