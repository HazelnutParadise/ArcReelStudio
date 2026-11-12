"""系列：项目之上的一层（docs/adr/0129）。

一个系列记三样东西：共用的设定（世界观、剧情设定）、属于它的项目、它共用的全局资产库条目。系列资产套用到项目时
走既有的 ``/assets/apply-to-project``，复制一份进项目，之后各自独立。所有成员都能读写系列，与项目同一口径。
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db import get_async_session
from lib.db.models.series import SERIES_NAME_MAX_LENGTH, SERIES_SETTING_MAX_LENGTH, Series
from lib.db.repositories.asset_repo import AssetRepository
from lib.db.repositories.series_repo import SeriesRepository
from lib.project.project_manager import get_project_manager
from server.i18n import Translator

router = APIRouter(prefix="/series", tags=["系列"])

Session = Annotated[AsyncSession, Depends(get_async_session)]


class SeriesView(BaseModel):
    id: int
    name: str
    description: str
    world_setting: str
    plot_setting: str
    #: 属于这个系列、且目前存在的项目（项目 ID）
    project_names: list[str]
    #: 这个系列共用的全局资产库条目 id
    asset_ids: list[str]
    updated_at: str | None


class SeriesListResponse(BaseModel):
    series: list[SeriesView]


class CreateSeriesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=SERIES_NAME_MAX_LENGTH)
    description: str = Field(default="", max_length=2000)


class UpdateSeriesRequest(BaseModel):
    """只改给出的字段。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=SERIES_NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=2000)
    world_setting: str | None = Field(default=None, max_length=SERIES_SETTING_MAX_LENGTH)
    plot_setting: str | None = Field(default=None, max_length=SERIES_SETTING_MAX_LENGTH)


async def _existing_projects() -> set[str]:
    return set(await asyncio.to_thread(get_project_manager().list_projects))


async def _view(repo: SeriesRepository, series: Series, existing: set[str]) -> SeriesView:
    return SeriesView(
        id=series.id,
        name=series.name,
        description=series.description,
        world_setting=series.world_setting,
        plot_setting=series.plot_setting,
        project_names=[name for name in await repo.project_names(series.id) if name in existing],
        asset_ids=await repo.asset_ids(series.id),
        updated_at=series.updated_at.isoformat() if series.updated_at else None,
    )


async def _require(repo: SeriesRepository, series_id: int, _t: Translator) -> Series:
    series = await repo.get(series_id)
    if series is None:
        raise HTTPException(status_code=404, detail=_t("series_not_found"))
    return series


def _clean_name(name: str, _t: Translator) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail=_t("series_name_required"))
    return cleaned


@router.get("", response_model=SeriesListResponse)
async def list_series(session: Session) -> SeriesListResponse:
    repo = SeriesRepository(session)
    existing = await _existing_projects()
    return SeriesListResponse(series=[await _view(repo, series, existing) for series in await repo.list()])


@router.post("", response_model=SeriesView, status_code=201)
async def create_series(body: CreateSeriesRequest, _t: Translator, session: Session) -> SeriesView:
    repo = SeriesRepository(session)
    name = _clean_name(body.name, _t)
    if await repo.get_by_name(name) is not None:
        raise HTTPException(status_code=409, detail=_t("series_name_conflict", name=name))
    try:
        series = await repo.create(name=name, description=body.description.strip())
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=_t("series_name_conflict", name=name)) from exc
    return await _view(repo, series, set())


@router.get("/{series_id}", response_model=SeriesView)
async def get_series(series_id: int, _t: Translator, session: Session) -> SeriesView:
    repo = SeriesRepository(session)
    return await _view(repo, await _require(repo, series_id, _t), await _existing_projects())


@router.patch("/{series_id}", response_model=SeriesView)
async def update_series(series_id: int, body: UpdateSeriesRequest, _t: Translator, session: Session) -> SeriesView:
    repo = SeriesRepository(session)
    series = await _require(repo, series_id, _t)
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in fields:
        fields["name"] = _clean_name(fields["name"], _t)
        other = await repo.get_by_name(fields["name"])
        if other is not None and other.id != series.id:
            raise HTTPException(status_code=409, detail=_t("series_name_conflict", name=fields["name"]))
    try:
        await repo.update(series, **fields)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=_t("series_name_conflict", name=fields.get("name", ""))) from exc
    return await _view(repo, series, await _existing_projects())


@router.delete("/{series_id}", status_code=204)
async def delete_series(series_id: int, _t: Translator, session: Session) -> None:
    """删除系列：它的项目回到不属于任何系列，项目本身与资产库里的资产都不受影响。"""
    repo = SeriesRepository(session)
    await _require(repo, series_id, _t)
    await repo.delete(series_id)
    await session.commit()


@router.put("/{series_id}/projects/{project_name}", response_model=SeriesView)
async def add_project(series_id: int, project_name: str, _t: Translator, session: Session) -> SeriesView:
    """把项目放进这个系列。一个项目至多属于一个系列：它原本在别的系列时改到这里。"""
    repo = SeriesRepository(session)
    series = await _require(repo, series_id, _t)
    existing = await _existing_projects()
    if project_name not in existing:
        raise HTTPException(status_code=404, detail=_t("series_project_not_found", name=project_name))
    await repo.set_project(series_id, project_name)
    await session.commit()
    return await _view(repo, series, existing)


@router.delete("/{series_id}/projects/{project_name}", response_model=SeriesView)
async def remove_project(series_id: int, project_name: str, _t: Translator, session: Session) -> SeriesView:
    repo = SeriesRepository(session)
    series = await _require(repo, series_id, _t)
    await repo.remove_project(series_id, project_name)
    await session.commit()
    return await _view(repo, series, await _existing_projects())


@router.put("/{series_id}/assets/{asset_id}", response_model=SeriesView)
async def add_asset(series_id: int, asset_id: str, _t: Translator, session: Session) -> SeriesView:
    repo = SeriesRepository(session)
    series = await _require(repo, series_id, _t)
    if await AssetRepository(session).get_by_id(asset_id) is None:
        raise HTTPException(status_code=404, detail=_t("series_asset_not_found"))
    await repo.add_asset(series_id, asset_id)
    await session.commit()
    return await _view(repo, series, await _existing_projects())


@router.delete("/{series_id}/assets/{asset_id}", response_model=SeriesView)
async def remove_asset(series_id: int, asset_id: str, _t: Translator, session: Session) -> SeriesView:
    repo = SeriesRepository(session)
    series = await _require(repo, series_id, _t)
    await repo.remove_asset(series_id, asset_id)
    await session.commit()
    return await _view(repo, series, await _existing_projects())
