"""Give job ids permanent AUTOINCREMENT

The transcode queue's ``id`` was a plain SQLite ``INTEGER PRIMARY KEY`` (a rowid
alias), so once the table emptied the next insert restarted at 1, reusing ids
from earlier jobs. Recreate the table with SQLite ``AUTOINCREMENT`` so the
highest-ever id is tracked in ``sqlite_sequence`` and never handed out again.

Existing rows are copied into the rebuilt table, so numbering continues from the
current max.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite can't add AUTOINCREMENT via ALTER TABLE; recreate the table
    # (batch mode copies existing rows over).
    with op.batch_alter_table(
        "transcode_queue",
        recreate="always",
        table_kwargs={"sqlite_autoincrement": True},
    ):
        pass


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("transcode_queue", recreate="always"):
        pass
