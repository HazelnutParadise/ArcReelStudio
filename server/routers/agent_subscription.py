"""Agent 的认证方式：用 Claude 订阅、API Key，或两者谁优先；以及 Agent 用哪一条 Claude 订阅连线。

Claude 订阅的连线在连线中心登录（``/providers/claude-subscription/logins``），这里只读状态、改认证方式与选连线。
认证方式与连线是整个工作区共用的，只有管理员能改。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from lib.agent.agent_auth import AUTH_MODE_SETTING_KEY, AuthMode, auth_availability, parse_auth_mode
from lib.config.repository import SystemSettingRepository
from lib.config.service import (
    AGENT_SUBSCRIPTION_CREDENTIAL_KEY,
    CLAUDE_SUBSCRIPTION_PROVIDER,
    agent_claude_subscription,
)
from lib.db import get_async_session
from lib.db.repositories.agent_credential_repo import AgentCredentialRepository
from lib.db.repositories.credential_repository import CredentialRepository
from server.auth import AdminUser
from server.i18n import Translator

router = APIRouter(prefix="/agent/subscription", tags=["Agent 配置"])


class SourceAvailability(BaseModel):
    """暂时不能用时的到期时间（Unix 秒）；要等重新配置时为 ``None`` 且 ``blocked`` 为真。"""

    blocked: bool
    until: float | None = None


class SubscriptionStatus(BaseModel):
    #: Agent 实际会用的 Claude 订阅连线；一条都没有时为 None
    credential_id: int | None = None
    credential_name: str | None = None
    #: 指定的连线（旁键）；没指定时为 None，用 Claude 订阅的默认连线
    chosen_credential_id: int | None = None
    mode: AuthMode
    has_api_key: bool
    subscription: SourceAvailability
    api_key: SourceAvailability


class ModeRequest(BaseModel):
    mode: Literal["api_key", "subscription", "prefer_subscription", "prefer_api_key"]


class ConnectionRequest(BaseModel):
    #: None 表示用 Claude 订阅的默认连线
    credential_id: int | None = None


def _availability(source: Literal["api_key", "subscription"]) -> SourceAvailability:
    until = auth_availability.unavailable_until(source)
    if until is None:
        return SourceAvailability(blocked=False)
    return SourceAvailability(blocked=True, until=None if until == float("inf") else until)


async def _status(session: AsyncSession) -> SubscriptionStatus:
    settings = await SystemSettingRepository(session).get_all()
    subscription = await agent_claude_subscription(session, settings)
    cred = await AgentCredentialRepository(session).get_active()
    has_api_key = bool(cred.api_key if cred is not None else settings.get("anthropic_api_key", "").strip())
    chosen = (settings.get(AGENT_SUBSCRIPTION_CREDENTIAL_KEY) or "").strip()
    return SubscriptionStatus(
        credential_id=subscription.id if subscription is not None else None,
        credential_name=subscription.name if subscription is not None else None,
        chosen_credential_id=int(chosen) if chosen.isdigit() else None,
        mode=parse_auth_mode(settings.get(AUTH_MODE_SETTING_KEY)),
        has_api_key=has_api_key,
        subscription=_availability("subscription"),
        api_key=_availability("api_key"),
    )


@router.get("", response_model=SubscriptionStatus)
async def get_subscription(session: AsyncSession = Depends(get_async_session)) -> SubscriptionStatus:
    return await _status(session)


@router.put("/mode", response_model=SubscriptionStatus)
async def set_mode(
    body: ModeRequest,
    _admin: AdminUser,
    _t: Translator,
    session: AsyncSession = Depends(get_async_session),
) -> SubscriptionStatus:
    if body.mode == "subscription" and await agent_claude_subscription(session) is None:
        raise HTTPException(status_code=422, detail=_t("claude_subscription_required"))
    await SystemSettingRepository(session).set(AUTH_MODE_SETTING_KEY, body.mode)
    await session.commit()
    return await _status(session)


@router.put("/connection", response_model=SubscriptionStatus)
async def set_connection(
    body: ConnectionRequest,
    _admin: AdminUser,
    _t: Translator,
    session: AsyncSession = Depends(get_async_session),
) -> SubscriptionStatus:
    settings_repo = SystemSettingRepository(session)
    if body.credential_id is None:
        await settings_repo.set(AGENT_SUBSCRIPTION_CREDENTIAL_KEY, "")
    else:
        cred = await CredentialRepository(session).get_by_id(body.credential_id)
        if cred is None or cred.provider != CLAUDE_SUBSCRIPTION_PROVIDER:
            raise HTTPException(status_code=422, detail=_t("subscription_credential_not_found"))
        await settings_repo.set(AGENT_SUBSCRIPTION_CREDENTIAL_KEY, str(body.credential_id))
    await session.commit()
    # 换了连线：之前记下的订阅额度用完不一定适用于这条
    auth_availability.clear("subscription")
    return await _status(session)
