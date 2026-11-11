"""免版权素材库在请求边界上的共用部分：当前成员可用的密钥、错误到 HTTP 的映射（docs/adr/0128）。"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db.models.stock_source_key import WORKSPACE_OWNER
from lib.db.repositories.stock_source_key_repo import StockSourceKeyRepository
from lib.stock.model import StockError, StockSource
from lib.stock.service import StockLibraryService
from server.i18n import Translator

_STATUS_BY_CODE: Mapping[str, int] = {
    "stock_unknown_source": 404,
    "stock_kind_unsupported": 400,
    "stock_key_missing": 400,
    "stock_key_rejected": 400,
    "stock_item_not_found": 404,
    "stock_source_failed": 502,
    "stock_download_rejected": 400,
    "stock_file_too_large": 400,
    "stock_file_unsupported": 400,
}


def stock_library() -> StockLibraryService:
    """FastAPI 依赖：素材库服务。测试经 ``dependency_overrides`` 换成接了假来源的实例。"""
    return StockLibraryService()


def key_owner(source: StockSource, account_id: str) -> str:
    """这个来源的密钥归谁：工作区共用的记在空串名下，成员自己的记在账号 id 名下。"""
    return account_id if source.key_scope == "member" else WORKSPACE_OWNER


async def stock_keys(session: AsyncSession, library: StockLibraryService, account_id: str) -> dict[str, str]:
    """当前成员搜索与导入时每个来源可用的密钥：来源 id → 密钥，没有密钥的来源不在其中。"""
    stored = await StockSourceKeyRepository(session).keys_for((WORKSPACE_OWNER, account_id))
    keys: dict[str, str] = {}
    for source in library.sources():
        key = stored.get((source.id, key_owner(source, account_id)))
        if key:
            keys[source.id] = key
    return keys


def stock_http_error(exc: StockError, _t: Translator) -> HTTPException:
    return HTTPException(status_code=_STATUS_BY_CODE[exc.code], detail=_t(exc.code, **exc.params))
