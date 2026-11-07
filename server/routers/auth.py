"""
认证 API 路由

提供 OAuth2 登录、token 验证、当前账号与修改自己密码的接口。
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from lib.db import async_session_factory
from lib.infra.api_errors import ApiError
from lib.infra.data_root_layout import DataRootLayout
from server.auth import (
    EMBEDDED_AGENT_SUB,
    CurrentUser,
    create_token,
    is_auth_enabled,
)
from server.i18n import Translator
from server.services import accounts

logger = logging.getLogger(__name__)

router = APIRouter()

# 公开端点：拿到 token 之前必须可达，注册时不挂 Bearer 依赖。
public_router = APIRouter()


# ==================== 响应模型 ====================


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class VerifyResponse(BaseModel):
    valid: bool
    username: str


class AuthStatusResponse(BaseModel):
    enabled: bool


class MeResponse(BaseModel):
    id: str
    username: str
    role: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ==================== 路由 ====================


@public_router.get("/auth/status", response_model=AuthStatusResponse)
async def auth_status():
    """暴露 ``AUTH_ENABLED`` 状态供前端 bootstrap 判断是否需要登录拦截。

    前端 ``auth-store.initialize()`` 在 localStorage 无 token 时调用本接口：
    ``enabled=false`` 时跳过登录页直接进主界面；``enabled=true`` 时保留原
    登录链路。本接口本身**不要求认证**——一个 boolean 比 401 探针更直观，
    且实际"是否需要登录"通过 401/200 也能从外部观察到，因此不增量泄露。
    """
    return AuthStatusResponse(enabled=is_auth_enabled())


@public_router.post("/auth/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    _t: Translator,
):
    """用户登录

    使用 OAuth2 标准表单格式验证凭据，成功返回 access_token。
    ``AUTH_ENABLED=false`` 时跳过凭据校验，直接签发 token，让前端
    LoginPage 即便被打开也能正常跳转主界面。
    """
    if not is_auth_enabled():
        return TokenResponse(access_token=create_token(form_data.username), token_type="bearer")

    async with async_session_factory() as session:
        user = await accounts.authenticate(session, form_data.username, form_data.password)
    if user is None:
        logger.warning("登录失败: 用户名或密码错误 (用户: %s)", form_data.username)
        raise HTTPException(
            status_code=401,
            detail=_t("unauthorized"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_token(user.username, user_id=user.id, token_version=user.token_version)
    logger.info("用户登录成功: %s", user.username)
    return TokenResponse(access_token=token, token_type="bearer")


@router.get("/auth/verify", response_model=VerifyResponse)
async def verify(
    current_user: CurrentUser,
):
    """验证 token 有效性

    使用 OAuth2 Bearer token 依赖自动提取和验证 token。
    """
    return VerifyResponse(valid=True, username=current_user.sub)


@router.get("/auth/me", response_model=MeResponse)
async def me(current_user: CurrentUser) -> MeResponse:
    """当前登录的账号；前端据此显示用户名，并决定是否展示成员管理。"""
    return MeResponse(id=current_user.id, username=current_user.sub, role=current_user.role)


@router.post("/auth/password", response_model=TokenResponse)
async def change_password(body: ChangePasswordRequest, current_user: CurrentUser) -> TokenResponse:
    """修改自己的密码，返回新的 token；其他设备上的登录随之失效。"""
    if current_user.sub == EMBEDDED_AGENT_SUB or current_user.sub.startswith("apikey:"):
        raise ApiError("jwt_auth_required", status_code=403)
    async with async_session_factory() as session, session.begin():
        user = await accounts.change_own_password(
            session,
            current_user.id,
            current_password=body.current_password,
            new_password=body.new_password,
            initial_password_path=DataRootLayout.current().initial_admin_password_path,
        )
        token = create_token(user.username, user_id=user.id, token_version=user.token_version)
    return TokenResponse(access_token=token, token_type="bearer")
