"""Agent 引擎设定的路由：读状态、切换引擎与 Codex 连线／模型，以及只有管理员能改。"""

from __future__ import annotations

import pytest_asyncio
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from lib.db import get_async_session
from lib.db.repositories.credential_repository import CredentialRepository
from server.auth import CurrentUserInfo, get_current_user
from server.error_handlers import register_error_handlers
from server.routers import agent_engine
from tests.auth_deps import AUTH_DEPENDENCIES

BASE = "/api/v1/agent/engine"


def _make_app(session_factory, role: str) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    async def override_session():
        async with session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="tester", role=role)
    app.include_router(agent_engine.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    return app


@pytest_asyncio.fixture
async def engine_admin(db_factory):
    async with AsyncClient(transport=ASGITransport(app=_make_app(db_factory, "admin")), base_url="http://t") as c:
        yield c


@pytest_asyncio.fixture
async def engine_member(db_factory):
    async with AsyncClient(transport=ASGITransport(app=_make_app(db_factory, "member")), base_url="http://t") as c:
        yield c


async def _add(db_factory, provider: str, name: str) -> int:
    async with db_factory() as session:
        cred = await CredentialRepository(session).create(provider=provider, name=name, api_key="secret")
        await session.commit()
        return cred.id


async def test_the_default_is_claude_with_no_codex_connection(engine_admin) -> None:
    body = (await engine_admin.get(BASE)).json()

    assert body["engine"] == "claude"
    assert body["codex_credential_id"] is None
    assert body["codex_effective_credential_id"] is None
    assert body["codex_model"] == "gpt-5.5"
    assert "gpt-6-sol" in body["codex_models"]


async def test_switching_to_codex_needs_a_connection(engine_admin, db_factory) -> None:
    rejected = await engine_admin.put(BASE, json={"engine": "codex"})
    assert rejected.status_code == 422

    chatgpt = await _add(db_factory, "chatgpt-subscription", "me")
    body = (await engine_admin.put(BASE, json={"engine": "codex", "codex_model": "gpt-6-sol"})).json()
    assert body["engine"] == "codex"
    assert body["codex_effective_credential_id"] == chatgpt
    assert body["codex_model"] == "gpt-6-sol"


async def test_a_chosen_connection_must_be_chatgpt_or_openai(engine_admin, db_factory) -> None:
    claude = await _add(db_factory, "claude-subscription", "c")
    openai = await _add(db_factory, "openai", "key")

    wrong = await engine_admin.put(BASE, json={"engine": "codex", "codex_credential_id": claude})
    assert wrong.status_code == 422
    body = (await engine_admin.put(BASE, json={"engine": "codex", "codex_credential_id": openai})).json()
    assert body["codex_credential_id"] == openai
    assert body["codex_effective_credential_id"] == openai


async def test_unknown_models_are_rejected(engine_admin, db_factory) -> None:
    await _add(db_factory, "openai", "key")

    response = await engine_admin.put(BASE, json={"engine": "codex", "codex_model": "gpt-2"})
    assert response.status_code == 422


async def test_members_can_read_but_not_change(engine_member, db_factory) -> None:
    await _add(db_factory, "openai", "key")

    assert (await engine_member.get(BASE)).status_code == 200
    assert (await engine_member.put(BASE, json={"engine": "codex"})).status_code == 403


async def test_switching_to_grok_needs_a_grok_connection(engine_admin, db_factory) -> None:
    assert (await engine_admin.put(BASE, json={"engine": "grok"})).status_code == 422

    xai = await _add(db_factory, "grok", "xai key")
    subscription = await _add(db_factory, "grok-subscription", "me")
    body = (await engine_admin.put(BASE, json={"engine": "grok", "grok_model": "grok-4.5"})).json()
    assert body["engine"] == "grok"
    assert body["grok_effective_credential_id"] == subscription
    assert body["grok_model"] == "grok-4.5"

    chosen = (await engine_admin.put(BASE, json={"engine": "grok", "grok_credential_id": xai})).json()
    assert chosen["grok_effective_credential_id"] == xai


async def test_grok_rejects_other_connections_and_unknown_models(engine_admin, db_factory) -> None:
    openai = await _add(db_factory, "openai", "key")
    await _add(db_factory, "grok-subscription", "me")

    assert (await engine_admin.put(BASE, json={"engine": "grok", "grok_credential_id": openai})).status_code == 422
    assert (await engine_admin.put(BASE, json={"engine": "grok", "grok_model": "grok-1"})).status_code == 422
