"""Add queue status transition timestamps

The status transition timestamp supports queue age, queue wait, and job attempt
duration metrics. Existing jobs start measuring from migration time.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table(
        "transcode_queue",
        table_kwargs={"sqlite_autoincrement": True},
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status_changed_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table(
        "transcode_queue",
        table_kwargs={"sqlite_autoincrement": True},
    ) as batch_op:
        batch_op.drop_column("status_changed_at")
