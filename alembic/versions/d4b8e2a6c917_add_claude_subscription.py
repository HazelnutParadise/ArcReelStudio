"""加 Claude 订阅令牌表。

Revision ID: d4b8e2a6c917
Revises: c3e9a7f1b204

Agent 可以用 Claude 订阅账号登录（``claude setup-token`` 换来的长效令牌），整个工作区共用一份。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4b8e2a6c917"
down_revision: str | Sequence[str] | None = "c3e9a7f1b204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_table("claude_subscriptions")
