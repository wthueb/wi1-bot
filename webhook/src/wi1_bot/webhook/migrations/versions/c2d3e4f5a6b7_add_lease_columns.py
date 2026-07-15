"""Add job-leasing columns to the transcode queue

The webhook now dispatches transcode jobs to replicable worker processes over
HTTP. A claimed job is leased (status/worker_id/lease_expires_at) so a crashed
worker's job is reclaimed once its lease expires; attempts bounds retries.

Revision ID: c2d3e4f5a6b7
Revises: b1f2c3d4e5a6
Create Date: 2026-07-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1f2c3d4e5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("transcode_queue") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(), nullable=False, server_default="queued")
        )
        batch_op.add_column(sa.Column("worker_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("transcode_queue") as batch_op:
        batch_op.drop_column("attempts")
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("worker_id")
        batch_op.drop_column("status")
