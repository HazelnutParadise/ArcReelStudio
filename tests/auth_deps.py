"""路由测试自行组装 FastAPI() 时复刻生产注册处的认证挂法。

``server/app.py`` 给受保护 router 挂 ``dependencies=[Depends(get_current_user)]``，
端点签名里不再声明 ``CurrentUser``。mini app 少挂这一层，测到的就是一个无认证的
应用——多数用例用 ``dependency_overrides`` 绕过认证，因而不会失败，只有断言 401
的用例会暴露。
"""

import asyncio
import os
import uuid

from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lib.db.base import DEFAULT_USER_ID
from server.auth import CurrentUserInfo, create_token, get_current_user

AUTH_DEPENDENCIES = [Depends(get_current_user)]


def default_admin_token() -> str:
    """全局测试库里默认管理员的会话 token；走真实 ``get_current_user`` 的用例用它带上登录态。"""
    return create_token("admin", user_id=DEFAULT_USER_ID, token_version=0)


def override_auth(app: FastAPI) -> None:
    """放行 mini app 的认证，等价于测试用户已登录。

    给不关心认证、只测业务行为的用例用；断言 401 的用例不要调它。
    """
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")


def seed_login_account(password: str, *, prefix: str = "tester", role: str = "admin") -> str:
    """在全局测试库里建一个能登录的账号并返回用户名，供走真实登录接口的同步用例使用。

    全局测试库跨用例共享：用户名带随机后缀，不碰默认管理员。用独立 engine 写入、用完即释放，
    不把连接留在应用 engine 的池里，也不依赖其他用例先跑过 lifespan。
    """
    from server.services import accounts

    username = f"{prefix}-{uuid.uuid4().hex[:8]}"

    async def seed() -> None:
        engine = create_async_engine(os.environ["DATABASE_URL"])
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session, session.begin():
                await accounts.create_account(session, username=username, password=password, role=role)
        finally:
            await engine.dispose()

    asyncio.run(seed())
    return username
