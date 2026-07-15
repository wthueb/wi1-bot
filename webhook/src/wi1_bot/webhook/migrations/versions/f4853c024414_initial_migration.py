"""Initial migration

Revision ID: f4853c024414
Revises:
Create Date: 2025-12-17 00:28:13.885985

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4853c024414"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "transcode_queue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("languages", sa.String(), nullable=True),
        sa.Column("video_params", sa.String(), nullable=True),
        sa.Column("audio_params", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("transcode_queue")
