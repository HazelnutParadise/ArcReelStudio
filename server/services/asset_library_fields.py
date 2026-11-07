"""全局资产库条目的文字字段（名称、描述、声音风格）修改：接口与协作写回走同一套校验。"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db.models.asset import Asset
from lib.db.repositories.asset_repo import AssetRepository
from lib.infra.api_errors import BadRequestError, ConflictError, NotFoundError
from lib.project.asset_types import validate_asset_name

#: 可以直接改的文字字段；图片与衍生另有接口
LIBRARY_ASSET_TEXT_FIELDS = ("name", "description", "voice_style")


async def update_library_asset_fields(session: AsyncSession, asset_id: str, changes: dict[str, str]) -> Asset:
    """改条目的文字字段并提交；不合规时抛 ``ApiError``，什么都不改。"""
    repo = AssetRepository(session)
    asset = await repo.get_by_id(asset_id)
    if asset is None:
        raise NotFoundError("asset_not_found", name=asset_id)
    patch = {field: changes[field] for field in LIBRARY_ASSET_TEXT_FIELDS if field in changes}
    if "name" in patch:
        try:
            patch["name"] = validate_asset_name(patch["name"])
        except ValueError as exc:
            raise BadRequestError("asset_invalid_name", name=patch["name"]) from exc
        if patch["name"] != asset.name and await repo.exists(asset.type, patch["name"]):
            raise ConflictError("asset_already_exists", name=patch["name"])
    try:
        asset = await repo.update(asset_id, **patch)
        await session.commit()
        await session.refresh(asset)
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("asset_already_exists", name=patch.get("name", "")) from exc
    return asset
