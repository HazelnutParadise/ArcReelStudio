"""账号表的读写。业务规则（角色、最后一个管理员、令牌失效）在 ``server.services.accounts``。"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from lib.db.models.user import User
from lib.db.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    async def get(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[User]:
        result = await self.session.execute(select(User).order_by(User.created_at, User.username))
        return list(result.scalars())

    async def any_with_password(self) -> bool:
        result = await self.session.execute(select(User.id).where(User.password_hash.is_not(None)).limit(1))
        return result.first() is not None

    async def count_active_admins(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))
        )
        return int(result.scalar_one())

    async def create(self, *, username: str, password_hash: str, role: str, user_id: str | None = None) -> User:
        user = User(
            id=user_id or uuid.uuid4().hex,
            username=username,
            role=role,
            is_active=True,
            password_hash=password_hash,
            token_version=0,
        )
        self.session.add(user)
        await self.session.flush()
        return user
