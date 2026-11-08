"""Codex 引擎会话端到端：SessionManager 用假 app-server 跑一轮，事件日志、会话引擎与恢复都与 Claude 引擎一致。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from lib.agent.credential_tiers import AgentPricing
from server.agent_runtime.codex_client import CodexSessionConfig
from server.agent_runtime.codex_engine import CodexLaunch
from server.agent_runtime.event_log import EventLogStore
from server.agent_runtime.session_manager import SessionManager
from server.agent_runtime.session_store import SessionMetaStore
from tests.codex_fakes import install_fake_codex, read_fake_codex_seen


@pytest.fixture
async def codex_manager(tmp_path, file_db_factory):
    return SessionManager(
        project_root=tmp_path,
        meta_store=SessionMetaStore(session_factory=file_db_factory),
        event_log_store=EventLogStore(session_factory=file_db_factory),
    )


def _launcher(tmp_path: Path, cli: str, calls: list[tuple[str, Any]]):
    async def caller(tool: str, arguments: Any) -> dict[str, Any]:
        calls.append((tool, arguments))
        return {"contentItems": [{"type": "inputText", "text": "projects: demo"}], "success": True}

    home = tmp_path / "codex-home"
    home.mkdir(exist_ok=True)

    async def build_codex(project_name: str, *, resume_thread_id: str | None = None, locale: str = "zh") -> CodexLaunch:
        config = CodexSessionConfig(
            codex_home=home,
            project_cwd=tmp_path,
            model="gpt-5.5",
            developer_instructions="rules",
            tool_specs=[{"type": "function", "name": "list_projects", "description": "d", "inputSchema": {}}],
            tool_callers={"list_projects": caller},
            arcreel_tool_names=frozenset({"list_projects"}),
            resume_thread_id=resume_thread_id,
            cli_path=cli,
        )
        pricing = AgentPricing(multiplier=0.0, provider_id="chatgpt-subscription", provider_credential_id=7)
        return CodexLaunch(config=config, pricing=pricing, auth_source="subscription")

    return build_codex


async def _entries(store: EventLogStore, session_id: str, count: int) -> list[dict[str, Any]]:
    for _ in range(250):
        entries = await store.list_after(session_id)
        if len(entries) >= count:
            return entries
        await asyncio.sleep(0.02)
    return await store.list_after(session_id)


async def _until_status(codex_manager: SessionManager, session_id: str, status: str) -> None:
    for _ in range(250):
        managed = codex_manager.sessions.get(session_id)
        if managed is not None and managed.status == status:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"{session_id} never reached {status}")


async def test_a_codex_session_runs_a_turn_through_the_event_log(codex_manager: SessionManager, tmp_path: Path) -> None:
    folder = tmp_path / "fake-codex"
    cli = install_fake_codex(folder, tool=True)
    calls: list[tuple[str, Any]] = []
    assembler = codex_manager._options_assembler
    with (
        patch.object(assembler, "read_engine", new=AsyncMock(return_value="codex")),
        patch.object(assembler, "build_codex", new=_launcher(tmp_path, cli, calls)),
    ):
        session_id = await codex_manager.send_new_session("demo", "帮我列出项目")
        assert session_id == "T1"
        await _until_status(codex_manager, session_id, "completed")
        entries = await _entries(codex_manager.event_log_store, session_id, 3)

        meta = await codex_manager.meta_store.get(session_id)
        assert meta is not None
        assert meta.engine == "codex"
        managed = codex_manager.sessions[session_id]
        assert managed.engine == "codex"
        assert managed.agent_pricing.provider_id == "chatgpt-subscription"
        await codex_manager.close_session(session_id)

    # 首条用户消息的日志条目由 AssistantService 受理时写入（直接调 SessionManager 时没有），与 Claude 引擎相同
    assert [e["type"] for e in entries] == ["assistant", "tool_result", "assistant"]
    assert [e["seq"] for e in entries] == sorted(e["seq"] for e in entries)
    assert entries[0]["content"][0]["name"] == "mcp__arcreel__list_projects"
    assert entries[1]["content"] == "projects: demo"
    assert entries[2]["content"][0]["text"] == "done U1"
    assert calls == [("list_projects", {"x": 1})]


async def test_a_codex_session_resumes_its_own_thread(codex_manager: SessionManager, tmp_path: Path) -> None:
    folder = tmp_path / "fake-codex"
    cli = install_fake_codex(folder)
    assembler = codex_manager._options_assembler
    with (
        patch.object(assembler, "read_engine", new=AsyncMock(return_value="codex")),
        patch.object(assembler, "build_codex", new=_launcher(tmp_path, cli, [])),
    ):
        session_id = await codex_manager.send_new_session("demo", "hi")
        await _until_status(codex_manager, session_id, "completed")
        await codex_manager.close_session(session_id)

        # 之后即使全局改回 Claude，恢复的仍是这个会话自己的 Codex thread
        assembler.read_engine.return_value = "claude"
        await codex_manager.send_message(session_id, "again")
        await _until_status(codex_manager, session_id, "completed")
        await codex_manager.close_session(session_id)

    seen = await asyncio.to_thread(read_fake_codex_seen, folder)
    threads = [r for r in seen["requests"] if r["method"] in ("thread/start", "thread/resume")]
    assert [r["method"] for r in threads][-1] == "thread/resume"
    assert threads[-1]["params"]["threadId"] == "T1"
