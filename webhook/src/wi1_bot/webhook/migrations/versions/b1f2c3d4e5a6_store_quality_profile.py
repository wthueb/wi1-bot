"""Store quality profile instead of transcoding params

The transcode queue now references a quality profile by name and records the
title's original language; the concrete ffmpeg parameters (video/audio params,
languages, fallback) are looked up from the profile at transcode time.

Any items already queued under the old schema cannot be mapped back to a profile
name, so the table is recreated (clearing the queue). Items are re-queued as new
downloads come in.

Revision ID: b1f2c3d4e5a6
Revises: f4853c024414
Create Date: 2026-07-10 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1f2c3d4e5a6"
down_revision: Union[str, Sequence[str], None] = "f4853c024414"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table("transcode_queue")
    op.create_table(
        "transcode_queue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("quality_profile", sa.String(), nullable=False),
        sa.Column("original_language", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("transcode_queue")
    op.create_table(
        "transcode_queue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("languages", sa.String(), nullable=True),
        sa.Column("video_params", sa.String(), nullable=True),
        sa.Column("audio_params", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
