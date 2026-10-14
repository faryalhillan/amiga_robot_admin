"""add rejection_reason column to requests

Revision ID: 0004
Revises: 0003
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "requests",
        sa.Column("rejection_reason", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("requests", "rejection_reason")
