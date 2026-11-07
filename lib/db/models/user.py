"""User model for multi-user infrastructure."""

import sqlalchemy as sa
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin

#: 账号角色：``admin`` 可以管理成员，``user`` 只能使用工作区。
USER_ROLES = ("admin", "user")


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=sa.true())
    # 为空表示该账号还不能登录（默认管理员在启动初始化前即如此）
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # 改密码、停用或改角色时加一，令牌里的版本不一致即失效
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
