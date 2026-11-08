"""Grok 引擎会话端到端：SessionManager + 真的本机工具端点 + 假 Grok ACP agent，事件日志、会话引擎与恢复与其他引擎一致。"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import uvicorn
from fastapi import FastAPI

from lib.agent.credential_tiers import AgentPricing
from server.agent_runtime.event_log import EventLogStore
from server.agent_runtime.grok_client import GrokSessionConfig
from server.agent_runtime.grok_engine import GrokLaunch
from server.agent_runtime.session_manager import SessionManager
from server.agent_runtime.session_store import SessionMetaStore
from server.agent_runtime.session_tool_endpoint import (
    SESSION_TOOL_PATH,
    SessionToolRegistry,
    router,
    session_tool_registry,
)
from tests.grok_fakes import install_fake_grok, read_fake_grok_seen


@pytest.fixture
async def grok_manager(tmp_path, file_db_factory):
    return SessionManager(
        project_root=tmp_path,
        meta_store=SessionMetaStore(session_factory=file_db_factory),
        event_log_store=EventLogStore(session_factory=file_db_factory),
    )


@pytest.fixture
async def endpoint() -> AsyncIterator[tuple[str, SessionToolRegistry]]:
    registry = session_tool_registry
    app = FastAPI()
    app.include_router(router)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"))
    task = asyncio.create_task(server.serve())
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}{SESSION_TOOL_PATH}", registry
    finally:
        server.should_exit = True
        with contextlib.suppress(Exception):
            await asyncio.wait_for(task, timeout=5)


def _launcher(tmp_path: Path, cli: str, url: str, registry: SessionToolRegistry, calls: list[tuple[str, Any]]):
    async def caller(tool: str, arguments: Any) -> dict[str, Any]:
        calls.append((tool, arguments))
        return {"contentItems": [{"type": "inputText", "text": "projects: demo"}], "success": True}

    home = tmp_path / "grok-home"
    home.mkdir(exist_ok=True)

    async def build_grok(project_name: str, *, resume_session_id: str | None = None, locale: str = "zh") -> GrokLaunch:
        config = GrokSessionConfig(
            grok_home=home,
            project_cwd=tmp_path,
            model="grok-4.6",
            rules="rules",
            tool_specs=[{"type": "function", "name": "list_projects", "description": "d", "inputSchema": {}}],
            tool_callers={"list_projects": caller},
            arcreel_tool_names=frozenset({"list_projects"}),
            tool_endpoint_url=url,
            resume_session_id=resume_session_id,
            cli_path=cli,
            registry=registry,
        )
        pricing = AgentPricing(multiplier=0.0, provider_id="grok-subscription", provider_credential_id=9)
        return GrokLaunch(config=config, pricing=pricing, auth_source="subscription")

    return build_grok


async def _entries(store: EventLogStore, session_id: str, count: int) -> list[dict[str, Any]]:
    for _ in range(250):
        entries = await store.list_after(session_id)
        if len(entries) >= count:
            return entries
        await asyncio.sleep(0.02)
    return await store.list_after(session_id)


async def _until_status(grok_manager: SessionManager, session_id: str, status: str) -> None:
    for _ in range(250):
        managed = grok_manager.sessions.get(session_id)
        if managed is not None and managed.status == status:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"{session_id} never reached {status}")


async def test_a_grok_session_runs_a_turn_through_the_event_log(
    grok_manager: SessionManager, endpoint, tmp_path: Path
) -> None:
    url, registry = endpoint
    cli = install_fake_grok(tmp_path / "fake", tool=True)
    calls: list[tuple[str, Any]] = []
    assembler = grok_manager._options_assembler
    with (
        patch.object(assembler, "read_engine", new=AsyncMock(return_value="grok")),
        patch.object(assembler, "build_grok", new=_launcher(tmp_path, cli, url, registry, calls)),
    ):
        session_id = await grok_manager.send_new_session("demo", "帮我列出项目")
        assert session_id == "G1"
        await _until_status(grok_manager, session_id, "completed")
        entries = await _entries(grok_manager.event_log_store, session_id, 4)
        meta = await grok_manager.meta_store.get(session_id)
        assert meta is not None
        assert meta.engine == "grok"
        assert grok_manager.sessions[session_id].agent_pricing.provider_id == "grok-subscription"
        await grok_manager.close_session(session_id)

    # 首条用户消息的日志条目由 AssistantService 受理时写入（直接调 SessionManager 时没有），与其他引擎相同
    assert [e["type"] for e in entries] == ["assistant", "assistant", "tool_result", "assistant"]
    assert entries[0]["content"][0]["text"] == "Let me check."
    assert entries[1]["content"][0]["name"] == "mcp__arcreel__list_projects"
    assert entries[2]["content"] == "projects: demo"
    assert entries[3]["content"][0]["text"] == "done"
    assert calls == [("list_projects", {"x": 1})]


async def test_a_grok_session_resumes_its_own_session(grok_manager: SessionManager, endpoint, tmp_path: Path) -> None:
    url, registry = endpoint
    folder = tmp_path / "fake"
    cli = install_fake_grok(folder)
    assembler = grok_manager._options_assembler
    with (
        patch.object(assembler, "read_engine", new=AsyncMock(return_value="grok")),
        patch.object(assembler, "build_grok", new=_launcher(tmp_path, cli, url, registry, [])),
    ):
        session_id = await grok_manager.send_new_session("demo", "hi")
        await _until_status(grok_manager, session_id, "completed")
        await grok_manager.close_session(session_id)

        assembler.read_engine.return_value = "claude"
        await grok_manager.send_message(session_id, "again")
        await _until_status(grok_manager, session_id, "completed")
        await grok_manager.close_session(session_id)

    seen = await asyncio.to_thread(read_fake_grok_seen, folder)
    opened = [r for r in seen["requests"] if r["method"] in ("session/new", "session/resume", "session/load")]
    assert opened[-1]["method"] == "session/resume"
    assert opened[-1]["params"]["sessionId"] == "G1"
