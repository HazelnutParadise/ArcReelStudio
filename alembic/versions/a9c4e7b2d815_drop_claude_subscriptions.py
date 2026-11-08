"""删 Claude 订阅令牌表：Claude 订阅改为连线中心里 ``claude-subscription`` 供应商的连线。

Revision ID: a9c4e7b2d815
Revises: e8a3c5f1d204

旧表里的令牌不搬：它没有账号信息，搬过去会多出一条认不出是谁的连线；需要的话在连线中心重新登录一次。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9c4e7b2d815"
down_revision: str | Sequence[str] | None = "e8a3c5f1d204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("claude_subscriptions")


def downgrade() -> None:
    op.create_table(
        "claude_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("oauth_token", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
