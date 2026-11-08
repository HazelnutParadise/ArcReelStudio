"""Agent 认证方式的路由：读状态、改方式、选哪一条 Claude 订阅连线，以及只有管理员能改。"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from lib.agent import agent_auth
from lib.agent.agent_auth import AuthAvailability
from lib.db import get_async_session
from lib.db.repositories.credential_repository import CredentialRepository
from server.auth import CurrentUserInfo, get_current_user
from server.error_handlers import register_error_handlers
from server.routers import agent_subscription
from tests.auth_deps import AUTH_DEPENDENCIES

BASE = "/api/v1/agent/subscription"


@pytest.fixture(autouse=True)
def fresh_availability(monkeypatch: pytest.MonkeyPatch) -> AuthAvailability:
    fresh = AuthAvailability()
    monkeypatch.setattr(agent_subscription, "auth_availability", fresh)
    monkeypatch.setattr(agent_auth, "auth_availability", fresh)
    return fresh


def _make_app(session_factory, role: str) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    async def override_session():
        async with session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="tester", role=role)
    app.include_router(agent_subscription.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    return app


@pytest_asyncio.fixture
async def admin_client(db_factory):
    async with AsyncClient(transport=ASGITransport(app=_make_app(db_factory, "admin")), base_url="http://t") as c:
        yield c


@pytest_asyncio.fixture
async def member_client(db_factory):
    async with AsyncClient(transport=ASGITransport(app=_make_app(db_factory, "member")), base_url="http://t") as c:
        yield c


async def _add_claude_connection(db_factory, name: str, token: str) -> int:
    async with db_factory() as session:
        cred = await CredentialRepository(session).create(provider="claude-subscription", name=name, api_key=token)
        await session.commit()
        return cred.id


async def test_status_without_a_subscription_connection(admin_client) -> None:
    body = (await admin_client.get(BASE)).json()

    assert body["credential_id"] is None
    assert body["mode"] == "prefer_subscription"
    assert body["subscription"] == {"blocked": False, "until": None}


async def test_status_uses_the_default_claude_connection_and_never_shows_the_token(admin_client, db_factory) -> None:
    first = await _add_claude_connection(db_factory, "Claude A", "sk-ant-oat01-secret-a")
    await _add_claude_connection(db_factory, "Claude B", "sk-ant-oat01-secret-b")

    resp = await admin_client.get(BASE)

    assert resp.json()["credential_id"] == first
    assert resp.json()["credential_name"] == "Claude A"
    assert "sk-ant-oat01" not in resp.text


async def test_choosing_a_connection_makes_the_agent_use_it(admin_client, db_factory) -> None:
    await _add_claude_connection(db_factory, "Claude A", "sk-ant-oat01-a")
    second = await _add_claude_connection(db_factory, "Claude B", "sk-ant-oat01-b")

    body = (await admin_client.put(f"{BASE}/connection", json={"credential_id": second})).json()

    assert (body["credential_id"], body["chosen_credential_id"]) == (second, second)
    cleared = (await admin_client.put(f"{BASE}/connection", json={"credential_id": None})).json()
    assert cleared["chosen_credential_id"] is None
    assert cleared["credential_name"] == "Claude A"


async def test_choosing_a_connection_of_another_provider_is_refused(admin_client, db_factory) -> None:
    async with db_factory() as session:
        other = await CredentialRepository(session).create(provider="openai", name="k", api_key="sk-x")
        await session.commit()

    resp = await admin_client.put(f"{BASE}/connection", json={"credential_id": other.id})

    assert resp.status_code == 422


async def test_subscription_only_mode_needs_a_connection(admin_client, db_factory) -> None:
    assert (await admin_client.put(f"{BASE}/mode", json={"mode": "subscription"})).status_code == 422

    await _add_claude_connection(db_factory, "Claude A", "sk-ant-oat01-a")
    body = (await admin_client.put(f"{BASE}/mode", json={"mode": "subscription"})).json()

    assert body["mode"] == "subscription"


async def test_members_can_read_but_not_change(member_client) -> None:
    assert (await member_client.get(BASE)).status_code == 200
    assert (await member_client.put(f"{BASE}/mode", json={"mode": "api_key"})).status_code == 403
    assert (await member_client.put(f"{BASE}/connection", json={"credential_id": None})).status_code == 403
