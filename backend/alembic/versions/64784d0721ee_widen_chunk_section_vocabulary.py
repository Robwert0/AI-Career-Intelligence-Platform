"""widen chunk section vocabulary

Revision ID: 64784d0721ee
Revises: abff6eff4eec
Create Date: 2026-08-16 23:11:04.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "64784d0721ee"
down_revision: str | Sequence[str] | None = "abff6eff4eec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Autogenerate cannot see CHECK constraint changes, so this revision is hand-written.
_OLD = "('experience', 'projects', 'skills')"
_NEW = (
    "('summary', 'experience', 'projects', 'skills', "
    "'education', 'certifications', 'languages', 'other')"
)


def _replace_section_check(values: str) -> None:
    op.drop_constraint("ck_chunks_section", "chunks", type_="check")
    op.create_check_constraint("ck_chunks_section", "chunks", f"section IN {values}")


def upgrade() -> None:
    """Upgrade schema."""
    _replace_section_check(_NEW)


def downgrade() -> None:
    """Downgrade schema."""
    # Rows in the widened sections violate the narrower constraint and would block this.
    op.execute(f"DELETE FROM chunks WHERE section NOT IN {_OLD}")
    _replace_section_check(_OLD)
