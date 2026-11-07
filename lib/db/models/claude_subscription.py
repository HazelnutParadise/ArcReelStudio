"""Claude 订阅登录换来的长效令牌（``claude setup-token`` 的结果）。

整个工作区共用一份：所有成员的 Agent 会话都用同一个 Claude 账号的订阅额度。令牌与 Agent 凭证的 API Key
一样以明文保存，读出 API 时脱敏。
"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import DEFAULT_USER_ID, Base, TimestampMixin


class ClaudeSubscription(TimestampMixin, Base):
    __tablename__ = "claude_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 工作区范围（恒为 default），每个工作区至多一条
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, default=DEFAULT_USER_ID)
    oauth_token: Mapped[str] = mapped_column(Text, nullable=False)
