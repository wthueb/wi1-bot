"""add seen_episodes

Revision ID: 8c1d4b7e2a90
Revises: 66eb12915b19
Create Date: 2026-08-02 02:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c1d4b7e2a90"
down_revision: Union[str, Sequence[str], None] = "66eb12915b19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "seen_episodes",
        sa.Column("tvdb_id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("tvdb_id", "episode_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("seen_episodes")
