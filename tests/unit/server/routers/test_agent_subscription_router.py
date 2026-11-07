"""Claude 订阅登录与认证方式的路由：登录、登出、改方式，以及只有管理员能动。"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from lib.agent import agent_auth
from lib.agent.agent_auth import AuthAvailability
from lib.agent.claude_subscription_login import ClaudeLoginManager
from lib.db import get_async_session
from lib.db.repositories.claude_subscription_repo import ClaudeSubscriptionRepository
from server.auth import CurrentUserInfo, get_current_user
from server.error_handlers import register_error_handlers
from server.routers import agent_subscription
from tests.auth_deps import AUTH_DEPENDENCIES
from tests.unit.lib.agent.test_claude_subscription_login import _FAKE_CLI, TOKEN

BASE = "/api/v1/agent/subscription"


@pytest.fixture(autouse=True)
def fresh_availability(monkeypatch: pytest.MonkeyPatch) -> AuthAvailability:
    fresh = AuthAvailability()
    monkeypatch.setattr(agent_subscription, "auth_availability", fresh)
    monkeypatch.setattr(agent_auth, "auth_availability", fresh)
    return fresh


def _make_app(session_factory, manager: ClaudeLoginManager, role: str) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    async def override_session():
        async with session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[agent_subscription.get_login_manager] = lambda: manager
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="tester", role=role)
    app.include_router(agent_subscription.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    return app


@pytest.fixture
def manager(tmp_path) -> ClaudeLoginManager:
    cli = tmp_path / "claude"
    cli.write_text(_FAKE_CLI, encoding="utf-8")
    cli.chmod(0o755)
    return ClaudeLoginManager(cli_path=str(cli))


@pytest_asyncio.fixture
async def admin_client(db_factory, manager):
    transport = ASGITransport(app=_make_app(db_factory, manager, "admin"))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await manager.cancel()


@pytest_asyncio.fixture
async def member_client(db_factory, manager):
    transport = ASGITransport(app=_make_app(db_factory, manager, "member"))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_status_starts_logged_out_with_the_default_mode(admin_client) -> None:
    resp = await admin_client.get(BASE)

    assert resp.status_code == 200
    body = resp.json()
    assert body["logged_in"] is False
    assert body["mode"] == "prefer_subscription"
    assert body["subscription"] == {"blocked": False, "until": None}


async def test_login_flow_stores_the_token_and_only_shows_it_masked(admin_client, db_factory) -> None:
    started = (await admin_client.post(f"{BASE}/login")).json()
    assert started["authorize_url"].startswith("https://claude.com/cai/oauth/authorize")

    resp = await admin_client.post(f"{BASE}/login/{started['login_id']}", json={"code": "good-code"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["logged_in"] is True
    assert TOKEN not in resp.text
    async with db_factory() as session:
        assert (await ClaudeSubscriptionRepository(session).get()).oauth_token == TOKEN


async def test_a_new_login_clears_an_earlier_quota_mark(admin_client, fresh_availability) -> None:
    fresh_availability.mark_unavailable("subscription", until=None)
    started = (await admin_client.post(f"{BASE}/login")).json()

    body = (await admin_client.post(f"{BASE}/login/{started['login_id']}", json={"code": "good-code"})).json()

    assert body["subscription"]["blocked"] is False


async def test_a_rejected_code_is_a_422_and_stores_nothing(admin_client, db_factory) -> None:
    started = (await admin_client.post(f"{BASE}/login")).json()

    resp = await admin_client.post(f"{BASE}/login/{started['login_id']}", json={"code": "bad-code"})

    assert resp.status_code == 422
    async with db_factory() as session:
        assert await ClaudeSubscriptionRepository(session).get() is None


async def test_subscription_only_needs_a_login_first(admin_client) -> None:
    resp = await admin_client.put(f"{BASE}/mode", json={"mode": "subscription"})

    assert resp.status_code == 422


async def test_mode_can_be_changed(admin_client) -> None:
    resp = await admin_client.put(f"{BASE}/mode", json={"mode": "prefer_api_key"})

    assert resp.status_code == 200
    assert resp.json()["mode"] == "prefer_api_key"
    assert (await admin_client.get(BASE)).json()["mode"] == "prefer_api_key"


async def test_logging_out_from_subscription_only_returns_to_the_default(admin_client) -> None:
    started = (await admin_client.post(f"{BASE}/login")).json()
    await admin_client.post(f"{BASE}/login/{started['login_id']}", json={"code": "good-code"})
    await admin_client.put(f"{BASE}/mode", json={"mode": "subscription"})

    body = (await admin_client.delete(BASE)).json()

    assert body["logged_in"] is False
    assert body["mode"] == "prefer_subscription"


async def test_members_can_read_the_status_but_not_change_it(member_client) -> None:
    assert (await member_client.get(BASE)).status_code == 200
    assert (await member_client.post(f"{BASE}/login")).status_code == 403
    assert (await member_client.put(f"{BASE}/mode", json={"mode": "api_key"})).status_code == 403
    assert (await member_client.delete(BASE)).status_code == 403
