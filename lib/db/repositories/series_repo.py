"""系列 repository。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select

from lib.db.models.asset import Asset
from lib.db.models.series import Series, SeriesAsset, SeriesProject
from lib.db.repositories.base import BaseRepository, rowcount


class SeriesRepository(BaseRepository):
    async def list(self) -> list[Series]:
        return list((await self.session.execute(select(Series).order_by(Series.created_at, Series.id))).scalars())

    async def get(self, series_id: int) -> Series | None:
        return await self.session.get(Series, series_id)

    async def get_by_name(self, name: str) -> Series | None:
        return (await self.session.execute(select(Series).where(Series.name == name))).scalar_one_or_none()

    async def create(self, *, name: str, description: str = "") -> Series:
        series = Series(name=name, description=description)
        self.session.add(series)
        await self.session.flush()
        return series

    async def update(self, series: Series, **fields: Any) -> Series:
        for key, value in fields.items():
            setattr(series, key, value)
        await self.session.flush()
        return series

    async def delete(self, series_id: int) -> None:
        # 关联表的外键是 ON DELETE CASCADE，但 SQLite 连接不一定开了外键约束：显式删掉，两种库行为一致
        await self.session.execute(delete(SeriesProject).where(SeriesProject.series_id == series_id))
        await self.session.execute(delete(SeriesAsset).where(SeriesAsset.series_id == series_id))
        await self.session.execute(delete(Series).where(Series.id == series_id))

    async def project_names(self, series_id: int) -> list[str]:
        stmt = (
            select(SeriesProject.project_name)
            .where(SeriesProject.series_id == series_id)
            .order_by(SeriesProject.created_at, SeriesProject.project_name)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def asset_ids(self, series_id: int) -> list[str]:
        """系列共用的资产 id，按加入先后。只返回资产库里还在的条目：删掉的资产不再算系列资产。"""
        stmt = (
            select(SeriesAsset.asset_id)
            .join(Asset, Asset.id == SeriesAsset.asset_id)
            .where(SeriesAsset.series_id == series_id)
            .order_by(SeriesAsset.created_at, SeriesAsset.asset_id)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def series_of_project(self, project_name: str) -> Series | None:
        stmt = select(Series).join(SeriesProject, SeriesProject.series_id == Series.id)
        stmt = stmt.where(SeriesProject.project_name == project_name)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def set_project(self, series_id: int, project_name: str) -> None:
        """把项目放进这个系列；它原本在别的系列时改到这里。"""
        row = await self.session.get(SeriesProject, project_name)
        if row is None:
            self.session.add(SeriesProject(project_name=project_name, series_id=series_id))
        else:
            row.series_id = series_id
        await self.session.flush()

    async def remove_project(self, series_id: int, project_name: str) -> bool:
        stmt = delete(SeriesProject).where(
            SeriesProject.series_id == series_id, SeriesProject.project_name == project_name
        )
        return rowcount(await self.session.execute(stmt)) > 0

    async def add_asset(self, series_id: int, asset_id: str) -> None:
        if await self.session.get(SeriesAsset, (series_id, asset_id)) is None:
            self.session.add(SeriesAsset(series_id=series_id, asset_id=asset_id))
            await self.session.flush()

    async def remove_asset(self, series_id: int, asset_id: str) -> bool:
        stmt = delete(SeriesAsset).where(SeriesAsset.series_id == series_id, SeriesAsset.asset_id == asset_id)
        return rowcount(await self.session.execute(stmt)) > 0
