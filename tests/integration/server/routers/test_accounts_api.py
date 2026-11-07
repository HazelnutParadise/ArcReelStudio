"""账号与成员管理接口：登录、当前账号、改自己的密码与管理员管理成员，走真实鉴权依赖与全局测试库。

全局测试库跨用例共享：每条用例新建用户名唯一的账号，不改默认管理员，其他用例签发的默认管理员 token 不受影响。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lib.db import async_session_factory
from server.auth import EMBEDDED_AGENT_SUB, create_token
from server.error_handlers import register_error_handlers
from server.routers import auth as auth_router
from server.routers import users as users_router
from server.services import accounts
from tests.auth_deps import AUTH_DEPENDENCIES


@pytest.fixture
async def accounts_client() -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(auth_router.public_router, prefix="/api/v1")
    app.include_router(auth_router.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    app.include_router(users_router.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    register_error_handlers(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _seed(role: str, password: str = "seed-password") -> str:
    username = _name(role)
    async with async_session_factory() as session, session.begin():
        await accounts.create_account(session, username=username, password=password, role=role)
    return username


async def _login(client: AsyncClient, username: str, password: str = "seed-password") -> str:
    response = await client.post("/api/v1/auth/token", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_members_log_in_and_see_their_own_account(accounts_client):
    username = await _seed("user")

    token = await _login(accounts_client, username.upper())
    me = await accounts_client.get("/api/v1/auth/me", headers=_bearer(token))

    assert me.status_code == 200
    assert me.json()["username"] == username
    assert me.json()["role"] == "user"


async def test_wrong_passwords_are_rejected(accounts_client):
    username = await _seed("user")

    response = await accounts_client.post("/api/v1/auth/token", data={"username": username, "password": "not-it"})

    assert response.status_code == 401


async def test_only_administrators_manage_members(accounts_client):
    member_token = await _login(accounts_client, await _seed("user"))
    agent_token = create_token(EMBEDDED_AGENT_SUB, expiry_seconds=60)

    for token in (member_token, agent_token):
        response = await accounts_client.get("/api/v1/users", headers=_bearer(token))
        assert response.status_code == 403


async def test_admins_add_members_who_can_then_log_in(accounts_client):
    admin_token = await _login(accounts_client, await _seed("admin"))
    username = _name("new")

    created = await accounts_client.post(
        "/api/v1/users",
        headers=_bearer(admin_token),
        json={"username": username, "password": "first-password", "role": "user"},
    )
    listed = await accounts_client.get("/api/v1/users", headers=_bearer(admin_token))

    assert created.status_code == 201
    assert created.json()["role"] == "user"
    assert username in {user["username"] for user in listed.json()}
    await _login(accounts_client, username, "first-password")


async def test_disabling_a_member_ends_their_sessions_and_blocks_login(accounts_client):
    admin_token = await _login(accounts_client, await _seed("admin"))
    username = await _seed("user")
    member_token = await _login(accounts_client, username)
    member_id = (await accounts_client.get("/api/v1/auth/me", headers=_bearer(member_token))).json()["id"]

    disabled = await accounts_client.patch(
        f"/api/v1/users/{member_id}", headers=_bearer(admin_token), json={"is_active": False}
    )

    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    assert (await accounts_client.get("/api/v1/auth/me", headers=_bearer(member_token))).status_code == 401
    login = await accounts_client.post("/api/v1/auth/token", data={"username": username, "password": "seed-password"})
    assert login.status_code == 401


async def test_admin_password_reset_replaces_the_members_password(accounts_client):
    admin_token = await _login(accounts_client, await _seed("admin"))
    username = await _seed("user")
    member_token = await _login(accounts_client, username)
    member_id = (await accounts_client.get("/api/v1/auth/me", headers=_bearer(member_token))).json()["id"]

    reset = await accounts_client.patch(
        f"/api/v1/users/{member_id}", headers=_bearer(admin_token), json={"password": "reset-password"}
    )

    assert reset.status_code == 200
    assert (await accounts_client.get("/api/v1/auth/me", headers=_bearer(member_token))).status_code == 401
    await _login(accounts_client, username, "reset-password")


async def test_changing_your_password_returns_a_new_session_and_ends_the_old_one(accounts_client):
    username = await _seed("user")
    old_token = await _login(accounts_client, username)

    wrong = await accounts_client.post(
        "/api/v1/auth/password",
        headers=_bearer(old_token),
        json={"current_password": "not-it", "new_password": "next-password"},
    )
    changed = await accounts_client.post(
        "/api/v1/auth/password",
        headers=_bearer(old_token),
        json={"current_password": "seed-password", "new_password": "next-password"},
    )

    assert wrong.status_code == 400
    assert changed.status_code == 200
    new_token = changed.json()["access_token"]
    assert (await accounts_client.get("/api/v1/auth/me", headers=_bearer(old_token))).status_code == 401
    assert (await accounts_client.get("/api/v1/auth/me", headers=_bearer(new_token))).status_code == 200
    await _login(accounts_client, username, "next-password")


async def test_invalid_member_input_is_explained(accounts_client):
    admin_token = await _login(accounts_client, await _seed("admin"))

    short = await accounts_client.post(
        "/api/v1/users", headers=_bearer(admin_token), json={"username": _name("x"), "password": "short"}
    )
    bad_name = await accounts_client.post(
        "/api/v1/users", headers=_bearer(admin_token), json={"username": "has space", "password": "long-enough"}
    )

    assert short.status_code == 400
    assert bad_name.status_code == 400
    assert short.json()["detail"] != bad_name.json()["detail"]
