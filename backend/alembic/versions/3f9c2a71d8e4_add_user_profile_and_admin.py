"""add user profile and admin columns

Revision ID: 3f9c2a71d8e4
Revises: 64784d0721ee
Create Date: 2026-10-05 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3f9c2a71d8e4"
down_revision: str | Sequence[str] | None = "64784d0721ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("company", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("role", sa.String(length=20), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("users", sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('recruiter', 'hiring_manager', 'engineer', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "last_active_at")
    op.drop_column("users", "is_admin")
    op.drop_column("users", "role")
    op.drop_column("users", "company")
