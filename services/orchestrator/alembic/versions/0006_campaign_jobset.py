"""Campaign JobSet cluster binding and submission completion index."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_campaign_jobset"
down_revision = "0005_user_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("k8s_jobset_name", sa.String(length=253), nullable=True),
    )
    op.add_column(
        "campaigns",
        sa.Column("k8s_jobset_uid", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "campaigns",
        sa.Column("items_configmap_name", sa.String(length=253), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("completion_index", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("submissions", "completion_index")
    op.drop_column("campaigns", "items_configmap_name")
    op.drop_column("campaigns", "k8s_jobset_uid")
    op.drop_column("campaigns", "k8s_jobset_name")
