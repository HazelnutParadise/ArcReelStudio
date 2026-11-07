"""成员管理 API：列出、新增成员，修改角色、启用状态或重设密码。只允许管理员本人以网页登录调用。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from lib.db import async_session_factory
from lib.db.models.user import User
from lib.infra.data_root_layout import DataRootLayout
from server.auth import AdminUser
from server.services import accounts

router = APIRouter()


class UserInfo(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool
    created_at: datetime

    @classmethod
    def of(cls, user: User) -> UserInfo:
        return cls(
            id=user.id,
            username=user.username,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: Literal["admin", "user"] = "user"


class UpdateUserRequest(BaseModel):
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None
    # 管理员替成员重设的新密码
    password: str | None = None


@router.get("/users", response_model=list[UserInfo])
async def list_users(_admin: AdminUser) -> list[UserInfo]:
    async with async_session_factory() as session:
        return [UserInfo.of(user) for user in await accounts.list_accounts(session)]


@router.post("/users", response_model=UserInfo, status_code=201)
async def create_user(body: CreateUserRequest, _admin: AdminUser) -> UserInfo:
    async with async_session_factory() as session, session.begin():
        user = await accounts.create_account(session, username=body.username, password=body.password, role=body.role)
        return UserInfo.of(user)


@router.patch("/users/{user_id}", response_model=UserInfo)
async def update_user(user_id: str, body: UpdateUserRequest, admin: AdminUser) -> UserInfo:
    async with async_session_factory() as session, session.begin():
        user = await accounts.update_account(
            session,
            actor_id=admin.id,
            user_id=user_id,
            role=body.role,
            is_active=body.is_active,
            password=body.password,
            initial_password_path=DataRootLayout.current().initial_admin_password_path,
        )
        return UserInfo.of(user)
