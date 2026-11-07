"""Claude 订阅令牌的读写；整个工作区一条。"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db.base import DEFAULT_USER_ID
from lib.db.models.claude_subscription import ClaudeSubscription
from lib.db.repositories.base import rowcount


class ClaudeSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: str = DEFAULT_USER_ID) -> ClaudeSubscription | None:
        result = await self.session.execute(select(ClaudeSubscription).where(ClaudeSubscription.user_id == user_id))
        return result.scalar_one_or_none()

    async def save_token(self, token: str, user_id: str = DEFAULT_USER_ID) -> ClaudeSubscription:
        """写入新令牌，已有一条时覆盖（重新登录换了账号或令牌）。"""
        row = await self.get(user_id)
        if row is None:
            row = ClaudeSubscription(user_id=user_id, oauth_token=token)
            self.session.add(row)
        else:
            row.oauth_token = token
        await self.session.flush()
        return row

    async def delete(self, user_id: str = DEFAULT_USER_ID) -> bool:
        result = await self.session.execute(delete(ClaudeSubscription).where(ClaudeSubscription.user_id == user_id))
        return rowcount(result) > 0
