"""免版权素材库在请求边界上的共用部分：当前成员可用的密钥、错误到 HTTP 的映射（docs/adr/0128）。"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db.models.stock_source_key import WORKSPACE_OWNER
from lib.db.repositories.stock_source_key_repo import StockSourceKeyRepository
from lib.stock.model import StockError, StockSource
from lib.stock.service import StockLibraryService
from server.auth import EMBEDDED_AGENT_SUB, CurrentUserInfo
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


def member_account(user: CurrentUserInfo) -> str | None:
    """这次调用代表的成员账号 id；内嵌 Agent 不代表任何成员，返回 ``None``。

    内嵌 Agent 的令牌解析出的 ``id`` 是预设管理员的账号 id，不能拿它当成员：否则 Agent 经 HTTP 就能用到、
    改掉那位管理员自己的 Freesound 密钥。
    """
    return None if user.sub == EMBEDDED_AGENT_SUB else user.id


def key_owner(source: StockSource, account_id: str) -> str:
    """这个来源的密钥归谁：工作区共用的记在空串名下，成员自己的记在账号 id 名下。"""
    return account_id if source.key_scope == "member" else WORKSPACE_OWNER


async def stock_keys(session: AsyncSession, library: StockLibraryService, account_id: str | None) -> dict[str, str]:
    """搜索与导入时每个来源可用的密钥：来源 id → 密钥，没有密钥的来源不在其中。

    ``account_id`` 为 ``None``（Agent）时只有工作区共用的密钥，成员自己的密钥一把都不给。
    """
    owners = (WORKSPACE_OWNER,) if account_id is None else (WORKSPACE_OWNER, account_id)
    stored = await StockSourceKeyRepository(session).keys_for(owners)
    keys: dict[str, str] = {}
    for source in library.sources():
        if source.key_scope == "member" and account_id is None:
            continue
        key = stored.get((source.id, key_owner(source, account_id or WORKSPACE_OWNER)))
        if key:
            keys[source.id] = key
    return keys


def stock_http_error(exc: StockError, _t: Translator) -> HTTPException:
    return HTTPException(status_code=_STATUS_BY_CODE[exc.code], detail=_t(exc.code, **exc.params))
