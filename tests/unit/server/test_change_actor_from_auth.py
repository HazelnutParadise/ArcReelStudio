"""认证依赖把登录的账号登记为本次请求里项目变更的发起成员，同步与异步处理函数都看得到。

内嵌 Agent 与关闭认证时的匿名用户不代表某位成员，不登记。
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from lib.db.base import DEFAULT_USER_ID
from lib.project.project_change_hints import get_project_change_actor
from server.auth import EMBEDDED_AGENT_SUB, create_token, get_current_user
from tests.auth_deps import AUTH_DEPENDENCIES, default_admin_token

_router = APIRouter()


@_router.get("/actor/sync")
def _sync_actor():
    return {"actor": get_project_change_actor()}


@_router.get("/actor/async")
async def _async_actor():
    return {"actor": get_project_change_actor()}


def _client(monkeypatch, token: str, *, auth_enabled: bool = True) -> TestClient:
    monkeypatch.setenv("AUTH_ENABLED", "true" if auth_enabled else "false")
    app = FastAPI()
    app.include_router(_router, dependencies=AUTH_DEPENDENCIES)
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


@pytest.mark.parametrize("path", ["/actor/sync", "/actor/async"])
async def test_the_signed_in_member_is_the_change_actor(monkeypatch, path):
    token = default_admin_token()
    client = _client(monkeypatch, token)
    username = (await get_current_user(token)).username

    assert username
    assert client.get(path).json() == {"actor": {"user_id": DEFAULT_USER_ID, "username": username}}


def test_the_embedded_agent_is_not_a_member(monkeypatch):
    client = _client(monkeypatch, create_token(EMBEDDED_AGENT_SUB))

    assert client.get("/actor/sync").json() == {"actor": None}


def test_requests_without_authentication_have_no_actor(monkeypatch):
    client = _client(monkeypatch, "ignored", auth_enabled=False)

    assert client.get("/actor/sync").json() == {"actor": None}
