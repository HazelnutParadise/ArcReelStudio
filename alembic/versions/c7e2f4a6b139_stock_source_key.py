"""免版权素材来源的密钥表。

Revision ID: c7e2f4a6b139
Revises: b5d8e1f3a027
Create Date: 2026-11-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c7e2f4a6b139"
down_revision = "b5d8e1f3a027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_source_key",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("owner", sa.String(), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_stock_source_key_source_owner", "stock_source_key", ["source", "owner"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_stock_source_key_source_owner", table_name="stock_source_key")
    op.drop_table("stock_source_key")
