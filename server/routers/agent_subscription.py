"""Claude 订阅登录与 Agent 认证方式（订阅、API Key 或两者谁优先）。

登录在网页上完成：后端跑 ``claude setup-token``，把授权链接给页面，用户在 claude.ai 授权后把验证码贴回来，
后端换到长效令牌存起来。订阅是整个工作区共用的，登录、登出与改认证方式只有管理员能做。
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lib.agent.agent_auth import (
    AUTH_MODE_SETTING_KEY,
    AuthMode,
    auth_availability,
    parse_auth_mode,
)
from lib.agent.claude_subscription_login import ClaudeLoginError, ClaudeLoginManager
from lib.config.repository import SystemSettingRepository, mask_secret
from lib.db import get_async_session
from lib.db.base import dt_to_iso
from lib.db.repositories.agent_credential_repo import AgentCredentialRepository
from lib.db.repositories.claude_subscription_repo import ClaudeSubscriptionRepository
from server.auth import AdminUser
from server.i18n import Translator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent/subscription", tags=["Agent 配置"])

_login_manager = ClaudeLoginManager()


def get_login_manager() -> ClaudeLoginManager:
    return _login_manager


class SourceAvailability(BaseModel):
    """暂时不能用时的到期时间（Unix 秒）；要等重新配置时为 ``None`` 且 ``blocked`` 为真。"""

    blocked: bool
    until: float | None = None


class SubscriptionStatus(BaseModel):
    logged_in: bool
    token_masked: str | None = None
    logged_in_at: str | None = None
    mode: AuthMode
    has_api_key: bool
    subscription: SourceAvailability
    api_key: SourceAvailability


class LoginStartResponse(BaseModel):
    login_id: str
    authorize_url: str


class LoginCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=4096)


class ModeRequest(BaseModel):
    mode: Literal["api_key", "subscription", "prefer_subscription", "prefer_api_key"]


def _availability(source: Literal["api_key", "subscription"]) -> SourceAvailability:
    until = auth_availability.unavailable_until(source)
    if until is None:
        return SourceAvailability(blocked=False)
    return SourceAvailability(blocked=True, until=None if until == float("inf") else until)


async def _status(session: AsyncSession) -> SubscriptionStatus:
    subscription = await ClaudeSubscriptionRepository(session).get()
    settings = await SystemSettingRepository(session).get_all()
    cred = await AgentCredentialRepository(session).get_active()
    has_api_key = bool(cred.api_key if cred is not None else settings.get("anthropic_api_key", "").strip())
    return SubscriptionStatus(
        logged_in=subscription is not None,
        token_masked=mask_secret(subscription.oauth_token) if subscription is not None else None,
        logged_in_at=dt_to_iso(subscription.updated_at) if subscription is not None else None,
        mode=parse_auth_mode(settings.get(AUTH_MODE_SETTING_KEY)),
        has_api_key=has_api_key,
        subscription=_availability("subscription"),
        api_key=_availability("api_key"),
    )


def _login_error(exc: ClaudeLoginError, _t: Translator) -> HTTPException:
    logger.warning("Claude 订阅登录失败 code=%s detail=%s", exc.code, exc.detail)
    status = 404 if exc.code in ("login_not_found", "login_expired") else 422
    if exc.code == "cli_not_found":
        status = 503
    return HTTPException(status_code=status, detail=_t(f"claude_login_{exc.code}"))


@router.get("", response_model=SubscriptionStatus)
async def get_subscription(session: AsyncSession = Depends(get_async_session)) -> SubscriptionStatus:
    return await _status(session)


@router.post("/login", response_model=LoginStartResponse)
async def start_login(
    _admin: AdminUser,
    _t: Translator,
    manager: ClaudeLoginManager = Depends(get_login_manager),
) -> LoginStartResponse:
    try:
        login_id, url = await manager.start()
    except ClaudeLoginError as exc:
        raise _login_error(exc, _t) from exc
    return LoginStartResponse(login_id=login_id, authorize_url=url)


@router.post("/login/{login_id}", response_model=SubscriptionStatus)
async def finish_login(
    login_id: str,
    body: LoginCodeRequest,
    _admin: AdminUser,
    _t: Translator,
    session: AsyncSession = Depends(get_async_session),
    manager: ClaudeLoginManager = Depends(get_login_manager),
) -> SubscriptionStatus:
    try:
        token = await manager.submit_code(login_id, body.code)
    except ClaudeLoginError as exc:
        raise _login_error(exc, _t) from exc
    await ClaudeSubscriptionRepository(session).save_token(token)
    await session.commit()
    # 新令牌：之前记下的额度用完或认证失败不再适用
    auth_availability.clear("subscription")
    return await _status(session)


@router.delete("/login", status_code=204)
async def cancel_login(_admin: AdminUser, manager: ClaudeLoginManager = Depends(get_login_manager)) -> None:
    await manager.cancel()


@router.delete("", response_model=SubscriptionStatus)
async def logout(_admin: AdminUser, session: AsyncSession = Depends(get_async_session)) -> SubscriptionStatus:
    await ClaudeSubscriptionRepository(session).delete()
    settings_repo = SystemSettingRepository(session)
    # 「只用订阅」却没有订阅了：回到默认（优先订阅，没有订阅时用 API Key）
    if parse_auth_mode((await settings_repo.get_all()).get(AUTH_MODE_SETTING_KEY)) == "subscription":
        await settings_repo.set(AUTH_MODE_SETTING_KEY, "prefer_subscription")
    await session.commit()
    auth_availability.clear("subscription")
    return await _status(session)


@router.put("/mode", response_model=SubscriptionStatus)
async def set_mode(
    body: ModeRequest,
    _admin: AdminUser,
    _t: Translator,
    session: AsyncSession = Depends(get_async_session),
) -> SubscriptionStatus:
    if body.mode == "subscription" and await ClaudeSubscriptionRepository(session).get() is None:
        raise HTTPException(status_code=422, detail=_t("claude_subscription_required"))
    await SystemSettingRepository(session).set(AUTH_MODE_SETTING_KEY, body.mode)
    await session.commit()
    return await _status(session)
