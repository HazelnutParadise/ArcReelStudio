"""连线中心的订阅登录路由：开始、贴码、轮询、取消，以及只有管理员能登录。"""

from __future__ import annotations

import asyncio

import pytest_asyncio
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from lib.db.repositories.credential_repository import CredentialRepository
from lib.subscriptions.device_login import DeviceLoginResult
from server.auth import CurrentUserInfo, get_current_user
from server.error_handlers import register_error_handlers
from server.routers import subscription_logins
from server.services.subscription_logins import SubscriptionLoginService
from tests.auth_deps import AUTH_DEPENDENCIES
from tests.subscription_fakes import FakeClaude, FakeDevice


def _make_app(service: SubscriptionLoginService, role: str) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.state.subscription_logins = service
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="tester", role=role)
    app.include_router(subscription_logins.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    return app


@pytest_asyncio.fixture
async def device(db_factory):
    return FakeDevice(DeviceLoginResult(status="succeeded", secret="{}", account_label="me@x.com (plus)"))


@pytest_asyncio.fixture
async def service(db_factory, device):
    svc = SubscriptionLoginService(
        db_factory,
        claude=FakeClaude(),  # type: ignore[arg-type]
        device_managers={"chatgpt-subscription": device},
        poll_interval=0.01,
    )
    yield svc
    await svc.close()


async def _client(service, role):
    return AsyncClient(transport=ASGITransport(app=_make_app(service, role)), base_url="http://t")


async def test_device_login_is_polled_until_the_connection_exists(service, device, db_factory) -> None:
    async with await _client(service, "admin") as client:
        started = (await client.post("/api/v1/providers/chatgpt-subscription/logins")).json()
        assert (started["kind"], started["user_code"], started["status"]) == ("device_code", "ABCD-1234", "pending")

        device.release.set()
        for _ in range(200):
            body = (await client.get(f"/api/v1/providers/chatgpt-subscription/logins/{started['login_id']}")).json()
            if body["status"] != "pending":
                break
            await asyncio.sleep(0.01)

    assert body["status"] == "succeeded"
    async with db_factory() as session:
        cred = await CredentialRepository(session).get_by_id(body["credential_id"])
    assert cred is not None
    assert cred.provider == "chatgpt-subscription"


async def test_claude_login_takes_the_pasted_code(service) -> None:
    async with await _client(service, "admin") as client:
        started = (await client.post("/api/v1/providers/claude-subscription/logins")).json()
        assert (started["kind"], started["user_code"]) == ("code_paste", None)

        done = await client.post(
            f"/api/v1/providers/claude-subscription/logins/{started['login_id']}/code", json={"code": "good"}
        )

    assert done.json()["status"] == "succeeded"
    assert "sk-ant-oat01" not in done.text


async def test_a_failed_login_explains_why(service) -> None:
    async with await _client(service, "admin") as client:
        started = (await client.post("/api/v1/providers/claude-subscription/logins")).json()
        done = (
            await client.post(
                f"/api/v1/providers/claude-subscription/logins/{started['login_id']}/code", json={"code": "bad"}
            )
        ).json()

    assert done["status"] == "failed"
    assert done["error"]


async def test_unknown_logins_and_non_subscription_providers_are_errors(service) -> None:
    async with await _client(service, "admin") as client:
        assert (await client.get("/api/v1/providers/chatgpt-subscription/logins/nope")).status_code == 404
        assert (await client.post("/api/v1/providers/openai/logins")).status_code == 422


async def test_cancel_forgets_the_login(service) -> None:
    async with await _client(service, "admin") as client:
        started = (await client.post("/api/v1/providers/chatgpt-subscription/logins")).json()
        path = f"/api/v1/providers/chatgpt-subscription/logins/{started['login_id']}"

        assert (await client.delete(path)).status_code == 204
        assert (await client.get(path)).status_code == 404


async def test_members_cannot_log_in(service) -> None:
    async with await _client(service, "member") as client:
        assert (await client.post("/api/v1/providers/chatgpt-subscription/logins")).status_code == 403
