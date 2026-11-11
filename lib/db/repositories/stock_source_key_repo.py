"""免版权素材来源密钥 repository。"""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from lib.db.models.stock_source_key import StockSourceKey
from lib.db.repositories.base import BaseRepository, rowcount


class StockSourceKeyRepository(BaseRepository):
    """按 ``(来源, 归属)`` 存取密钥；归属是空串（工作区共用）或成员的账号 id。"""

    async def keys_for(self, owners: tuple[str, ...]) -> dict[tuple[str, str], str]:
        """这些归属名下的全部密钥，键是 ``(来源, 归属)``。"""
        stmt = select(StockSourceKey).where(StockSourceKey.owner.in_(owners))
        rows = (await self.session.execute(stmt)).scalars().all()
        return {(row.source, row.owner): row.api_key for row in rows}

    async def save(self, *, source: str, owner: str, api_key: str) -> None:
        """写入一把密钥：已有就更新。并发的两次首次保存里，后到的一方撞上唯一索引后改为更新。"""
        if await self._update(source, owner, api_key):
            return
        try:
            async with self.session.begin_nested():
                self.session.add(StockSourceKey(source=source, owner=owner, api_key=api_key))
        except IntegrityError:
            await self._update(source, owner, api_key)

    async def _update(self, source: str, owner: str, api_key: str) -> bool:
        stmt = (
            update(StockSourceKey)
            .where(StockSourceKey.source == source, StockSourceKey.owner == owner)
            .values(api_key=api_key)
        )
        return rowcount(await self.session.execute(stmt)) > 0

    async def remove(self, *, source: str, owner: str) -> bool:
        stmt = delete(StockSourceKey).where(StockSourceKey.source == source, StockSourceKey.owner == owner)
        return rowcount(await self.session.execute(stmt)) > 0
