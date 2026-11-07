"""用户表加登录凭据：密码哈希与令牌版本。

Revision ID: c3e9a7f1b204
Revises: f6d2a8c4b931

``password_hash`` 为空表示该账号还不能登录；默认管理员 ``default`` 的密码由启动时的初始化步骤写入。
``token_version`` 在改密码、停用或改角色时加一，旧版本的会话令牌随之失效。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3e9a7f1b204"
down_revision: str | Sequence[str] | None = "f6d2a8c4b931"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("token_version")
        batch_op.drop_column("password_hash")
