"""agent_sessions 记下跑会话的 Agent 引擎（claude / codex）。

Revision ID: b5d8e1f3a027
Revises: a9c4e7b2d815
Create Date: 2026-11-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b5d8e1f3a027"
down_revision = "a9c4e7b2d815"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch:
        batch.add_column(sa.Column("engine", sa.String(), server_default="claude", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch:
        batch.drop_column("engine")
