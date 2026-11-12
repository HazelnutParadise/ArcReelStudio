"""系列：项目之上的一层，共用世界观、剧情设定与一组资产。

Revision ID: d4a8c1e6f250
Revises: c7e2f4a6b139
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d4a8c1e6f250"
down_revision = "c7e2f4a6b139"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("world_setting", sa.Text(), nullable=False),
        sa.Column("plot_setting", sa.Text(), nullable=False),
        *_timestamps(),
    )
    op.create_index("uq_series_name", "series", ["name"], unique=True)
    op.create_table(
        "series_project",
        sa.Column("project_name", sa.String(length=200), primary_key=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_series_project_series_id", "series_project", ["series_id"])
    op.create_table(
        "series_asset",
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("asset_id", sa.String(length=36), sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
        *_timestamps(),
    )


def downgrade() -> None:
    op.drop_table("series_asset")
    op.drop_index("ix_series_project_series_id", table_name="series_project")
    op.drop_table("series_project")
    op.drop_index("uq_series_name", table_name="series")
    op.drop_table("series")
