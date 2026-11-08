"""在连线中心登录订阅：每次登录成功就建立（或更新同一账号的）一条连线。

- Claude（``code_paste``）：返回授权链接，用户在 claude.ai 授权后把验证码贴回 ``.../code``。
- ChatGPT、Grok（``device_code``）：返回网址与一次性代码，用户在自己的浏览器授权；页面轮询 ``GET`` 看结果。

订阅连线由整个工作区共用，登录只有管理员能做。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from server.auth import AdminUser
from server.i18n import Translator
from server.services.subscription_logins import (
    LoginRecord,
    SubscriptionLoginService,
    SubscriptionLoginServiceError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/providers/{provider_id}/logins", tags=["供应商管理"])

_NOT_FOUND_CODES = frozenset({"login_not_found", "login_expired"})
_UNAVAILABLE_CODES = frozenset({"cli_unavailable", "cli_not_found"})


class LoginOut(BaseModel):
    login_id: str
    provider_id: str
    kind: Literal["code_paste", "device_code"]
    url: str
    user_code: str | None = None
    expires_at: datetime
    status: Literal["pending", "succeeded", "failed"]
    credential_id: int | None = None
    #: 失败时给界面显示的说明
    error: str | None = None


class LoginCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=4096)


def get_login_service(request: Request) -> SubscriptionLoginService:
    service = getattr(request.app.state, "subscription_logins", None)
    if service is None:
        raise HTTPException(status_code=503, detail="subscription login service is not running")
    return service


def _out(record: LoginRecord, _t: Translator) -> LoginOut:
    return LoginOut(
        login_id=record.login_id,
        provider_id=record.provider_id,
        kind=record.kind,
        url=record.url,
        user_code=record.user_code,
        expires_at=record.expires_at,
        status=record.state,
        credential_id=record.credential_id,
        error=_t(f"subscription_login_{record.error_code}") if record.error_code else None,
    )


def _http_error(exc: SubscriptionLoginServiceError, _t: Translator) -> HTTPException:
    logger.warning("订阅登录失败 code=%s detail=%s", exc.code, exc.detail)
    if exc.code in _NOT_FOUND_CODES:
        status = 404
    elif exc.code in _UNAVAILABLE_CODES:
        status = 503
    else:
        status = 422
    return HTTPException(status_code=status, detail=_t(f"subscription_login_{exc.code}"))


@router.post("", response_model=LoginOut)
async def start_login(
    provider_id: str,
    _admin: AdminUser,
    _t: Translator,
    service: SubscriptionLoginService = Depends(get_login_service),
) -> LoginOut:
    try:
        record = await service.start(provider_id)
    except SubscriptionLoginServiceError as exc:
        raise _http_error(exc, _t) from exc
    return _out(record, _t)


@router.get("/{login_id}", response_model=LoginOut)
async def get_login(
    provider_id: str,
    login_id: str,
    _admin: AdminUser,
    _t: Translator,
    service: SubscriptionLoginService = Depends(get_login_service),
) -> LoginOut:
    try:
        return _out(service.get(provider_id, login_id), _t)
    except SubscriptionLoginServiceError as exc:
        raise _http_error(exc, _t) from exc


@router.post("/{login_id}/code", response_model=LoginOut)
async def submit_code(
    provider_id: str,
    login_id: str,
    body: LoginCodeRequest,
    _admin: AdminUser,
    _t: Translator,
    service: SubscriptionLoginService = Depends(get_login_service),
) -> LoginOut:
    try:
        record = await service.submit_code(provider_id, login_id, body.code)
    except SubscriptionLoginServiceError as exc:
        raise _http_error(exc, _t) from exc
    return _out(record, _t)


@router.delete("/{login_id}", status_code=204)
async def cancel_login(
    provider_id: str,
    login_id: str,
    _admin: AdminUser,
    service: SubscriptionLoginService = Depends(get_login_service),
) -> Response:
    await service.cancel(provider_id, login_id)
    return Response(status_code=204)
