"""免版权素材库：来源与密钥、搜索、取图片档案（docs/adr/0128）。

只列不用署名就能商用的素材。Pixabay 与 Pexels 的密钥整个工作区共用，由管理员设置；Freesound 的密钥每位成员
各自设置，只在这位成员搜索与导入时使用。把音乐或音效导入项目见 ``files.py`` 的 ``/projects/{name}/stock/import``。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lib.config.repository import mask_secret
from lib.db import get_async_session
from lib.db.repositories.stock_source_key_repo import StockSourceKeyRepository
from lib.stock.model import KeyScope, StockError, StockKind, StockSource
from lib.stock.service import StockLibraryService, StockSearchResult
from server.auth import CurrentUser
from server.i18n import Translator
from server.services.stock_access import key_owner, stock_http_error, stock_keys, stock_library

router = APIRouter(prefix="/stock", tags=["素材库"])

_IMAGE_MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

Library = Annotated[StockLibraryService, Depends(stock_library)]
Session = Annotated[AsyncSession, Depends(get_async_session)]


class StockSourceView(BaseModel):
    id: str
    display_name: str
    kinds: list[StockKind]
    key_scope: KeyScope
    key_url: str | None
    #: 当前成员能不能用这个来源：不需要密钥，或者它的密钥已经设置
    available: bool
    key_masked: str | None
    #: 当前成员能不能设置这个来源的密钥：成员自己的密钥人人可设，工作区共用的只有管理员可设
    can_set_key: bool


class StockSourcesResponse(BaseModel):
    sources: list[StockSourceView]


class StockKeyRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)


def _can_set_key(source: StockSource, user: CurrentUser) -> bool:
    return source.key_scope == "member" or (source.key_scope == "workspace" and user.role == "admin")


async def _sources(session: AsyncSession, library: StockLibraryService, user: CurrentUser) -> StockSourcesResponse:
    keys = await stock_keys(session, library, user.id)
    return StockSourcesResponse(
        sources=[
            StockSourceView(
                id=source.id,
                display_name=source.display_name,
                kinds=sorted(source.kinds),
                key_scope=source.key_scope,
                key_url=source.key_url,
                available=source.key_scope == "none" or source.id in keys,
                key_masked=mask_secret(keys[source.id]) if source.id in keys else None,
                can_set_key=_can_set_key(source, user),
            )
            for source in library.sources()
        ]
    )


def _settable_source(library: StockLibraryService, source_id: str, user: CurrentUser, _t: Translator) -> StockSource:
    try:
        source = library.source(source_id)
    except StockError as exc:
        raise stock_http_error(exc, _t) from exc
    if source.key_scope == "none":
        raise HTTPException(status_code=400, detail=_t("stock_source_needs_no_key", source=source.display_name))
    if not _can_set_key(source, user):
        raise HTTPException(status_code=403, detail=_t("stock_key_admin_only", source=source.display_name))
    return source


@router.get("/sources", response_model=StockSourcesResponse)
async def list_sources(user: CurrentUser, library: Library, session: Session) -> StockSourcesResponse:
    return await _sources(session, library, user)


@router.put("/sources/{source_id}/key", response_model=StockSourcesResponse)
async def set_source_key(
    source_id: str, body: StockKeyRequest, user: CurrentUser, _t: Translator, library: Library, session: Session
) -> StockSourcesResponse:
    source = _settable_source(library, source_id, user, _t)
    api_key = body.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=422, detail=_t("stock_key_missing", source=source.display_name))
    await StockSourceKeyRepository(session).save(source=source.id, owner=key_owner(source, user.id), api_key=api_key)
    await session.commit()
    return await _sources(session, library, user)


@router.delete("/sources/{source_id}/key", response_model=StockSourcesResponse)
async def delete_source_key(
    source_id: str, user: CurrentUser, _t: Translator, library: Library, session: Session
) -> StockSourcesResponse:
    source = _settable_source(library, source_id, user, _t)
    await StockSourceKeyRepository(session).remove(source=source.id, owner=key_owner(source, user.id))
    await session.commit()
    return await _sources(session, library, user)


@router.get("/search", response_model=StockSearchResult)
async def search(
    user: CurrentUser,
    library: Library,
    session: Session,
    kind: StockKind,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    page: Annotated[int, Query(ge=1, le=50)] = 1,
) -> StockSearchResult:
    """问所有提供这种素材的来源。某个来源缺密钥或失败时照常返回其他来源的结果，状态写在 ``sources`` 里。"""
    keys = await stock_keys(session, library, user.id)
    return await library.search(kind=kind, query=q.strip(), page=page, keys=keys)


@router.get("/image")
async def fetch_image(
    user: CurrentUser,
    _t: Translator,
    library: Library,
    session: Session,
    source: Annotated[str, Query(min_length=1, max_length=32)],
    id: Annotated[str, Query(min_length=1, max_length=128)],
) -> Response:
    """取一张素材图片的档案。页面拿到后经现有的图片上传接口存进项目，与使用者自己上传的图片走同一条路。"""
    keys = await stock_keys(session, library, user.id)
    try:
        file = await library.fetch(source_id=source, kind="image", item_id=id, key=keys.get(source))
    except StockError as exc:
        raise stock_http_error(exc, _t) from exc
    return Response(
        content=file.content,
        media_type=_IMAGE_MEDIA_TYPES.get(file.extension, "application/octet-stream"),
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
