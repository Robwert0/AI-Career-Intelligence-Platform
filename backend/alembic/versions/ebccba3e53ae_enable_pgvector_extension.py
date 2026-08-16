"""enable pgvector extension

Revision ID: ebccba3e53ae
Revises: 842eb6337d5f
Create Date: 2026-08-16 21:37:43.948787

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ebccba3e53ae"
down_revision: str | Sequence[str] | None = "842eb6337d5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Downgrade schema."""
    # Deliberately not DROP EXTENSION: it is database-wide, so dropping it would cascade into
    # any other schema using vector columns. Downgrading this revision only needs to undo the
    # revisions above it — the extension is harmless left in place.
