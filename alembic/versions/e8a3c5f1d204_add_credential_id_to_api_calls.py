"""用量记录加上实际用的连线（凭证 id）。

Revision ID: e8a3c5f1d204
Revises: d4b8e2a6c917

同一供应商可以有多个连线、每个用到模型的地方可以各自指定。记下这次调用花在哪个连线上，按账号看用量与之后
「额度用完换连线」都靠它。是历史快照：连线删除后照样保留原 id，不设外键。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8a3c5f1d204"
down_revision: str | Sequence[str] | None = "d4b8e2a6c917"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("api_calls") as batch:
        batch.add_column(sa.Column("credential_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("api_calls") as batch:
        batch.drop_column("credential_id")
