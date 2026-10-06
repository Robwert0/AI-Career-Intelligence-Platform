"""backfill last_active_at from refresh tokens

Revision ID: 7c1e5b9a2d40
Revises: 3f9c2a71d8e4
Create Date: 2026-10-05 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c1e5b9a2d40"
down_revision: str | Sequence[str] | None = "3f9c2a71d8e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Accounts that predate last_active_at would otherwise be purged on their sign-up date alone.
BACKFILL_LAST_ACTIVE_SQL = """
UPDATE users
SET last_active_at = sub.max_created
FROM (
    SELECT user_id, max(created_at) AS max_created
    FROM refresh_tokens
    GROUP BY user_id
) sub
WHERE users.id = sub.user_id AND users.last_active_at IS NULL
"""


def upgrade() -> None:
    op.execute(sa.text(BACKFILL_LAST_ACTIVE_SQL))


def downgrade() -> None:
    # A backfilled value can't be told apart from a real one, so there is nothing to undo.
    pass
