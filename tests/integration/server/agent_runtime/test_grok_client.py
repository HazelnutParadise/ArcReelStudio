"""Grok 引擎 client：假 ACP agent 经真的本机工具端点呼叫工具，client 吐出的帧都能被 SDK 解析；Grok 自带工具被移除与拒绝。"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, UserMessage
from fastapi import FastAPI

from server.agent_runtime import sdk_frames, session_tool_endpoint
from server.agent_runtime.grok_client import (
    DISALLOWED_GROK_TOOLS,
    GROK_PERMISSION_CONFIG,
    GrokAgentClient,
    GrokSessionConfig,
)
from server.agent_runtime.sdk_frames import CommandLifecycle
from server.agent_runtime.session_tool_endpoint import SESSION_TOOL_PATH, SessionToolRegistry, router
from tests.grok_fakes import install_fake_grok, read_fake_grok_seen


@pytest.fixture
async def tool_server(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[str, SessionToolRegistry]]:
    registry = SessionToolRegistry()
    monkeypatch.setattr(session_tool_endpoint, "session_tool_registry", registry)
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


def _config(
    tmp_path: Path, cli: str, url: str, registry: SessionToolRegistry, **overrides: Any
) -> tuple[GrokSessionConfig, list[tuple[str, Any]]]:
    calls: list[tuple[str, Any]] = []

    async def caller(tool: str, arguments: Any) -> dict[str, Any]:
        calls.append((tool, arguments))
        return {"contentItems": [{"type": "inputText", "text": "projects: demo"}], "success": True}

    home = tmp_path / "grok-home"
    home.mkdir(exist_ok=True)
    fields: dict[str, Any] = {
        "grok_home": home,
        "project_cwd": tmp_path,
        "model": "grok-4.6",
        "rules": "answer in Chinese",
        "tool_specs": [
            {"type": "function", "name": "list_projects", "description": "d", "inputSchema": {"type": "object"}}
        ],
        "tool_callers": {"list_projects": caller},
        "arcreel_tool_names": frozenset({"list_projects"}),
        "tool_endpoint_url": url,
        "cli_path": cli,
        "registry": registry,
    }
    fields.update(overrides)
    return GrokSessionConfig(**fields), calls


async def _one(message: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    yield message


def _user(text: str, uid: str) -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": text}, "uuid": uid, "session_id": ""}


async def _until_idle(client: GrokAgentClient, idles: int = 1) -> list[Any]:
    parsed: list[Any] = []
    seen_idle = 0

    async def run() -> None:
        nonlocal seen_idle
        async for frame in sdk_frames.raw_frames(client):
            item = sdk_frames.parse_frame(frame)
            parsed.append(item)
            if (
                isinstance(item, SystemMessage)
                and item.subtype == "session_state_changed"
                and item.data.get("state") == "idle"
            ):
                seen_idle += 1
                if seen_idle >= idles:
                    return

    await asyncio.wait_for(run(), timeout=20)
    return parsed


async def test_a_turn_with_a_tool_call_becomes_sdk_frames(tool_server, tmp_path: Path) -> None:
    url, registry = tool_server
    folder = tmp_path / "fake"
    config, calls = _config(tmp_path, install_fake_grok(folder, tool=True), url, registry)
    async with GrokAgentClient(config) as client:
        await client.query(_one(_user("hi", "u-1")))
        frames = await _until_idle(client)

    assert isinstance(frames[0], SystemMessage)
    assert frames[0].data["session_id"] == "G1"
    texts = [b.text for f in frames if isinstance(f, AssistantMessage) for b in f.content if hasattr(b, "text")]
    assert texts == ["Let me check.", "done"]
    tool_use = next(
        b
        for f in frames
        if isinstance(f, AssistantMessage)
        for b in f.content
        if b.__class__.__name__ == "ToolUseBlock"
    )
    assert (tool_use.name, tool_use.input) == ("mcp__arcreel__list_projects", {"x": 1})
    tool_result = next(f for f in frames if isinstance(f, UserMessage))
    assert tool_result.content[0].tool_use_id == tool_use.id
    assert tool_result.content[0].content == "projects: demo"
    result = next(f for f in frames if isinstance(f, ResultMessage))
    assert (result.subtype, result.is_error, result.result) == ("success", False, "done")
    assert [(f.command_uuid, f.state) for f in frames if isinstance(f, CommandLifecycle)] == [
        ("u-1", "started"),
        ("u-1", "completed"),
    ]
    assert calls == [("list_projects", {"x": 1})]
    seen = await asyncio.to_thread(read_fake_grok_seen, folder)
    assert seen["tool_results"][0]["result"]["content"] == [{"type": "text", "text": "projects: demo"}]


async def test_grok_is_started_without_its_own_tools_and_with_our_endpoint(tool_server, tmp_path: Path) -> None:
    url, registry = tool_server
    folder = tmp_path / "fake"
    config, _ = _config(tmp_path, install_fake_grok(folder), url, registry)
    async with GrokAgentClient(config):
        pass

    seen = await asyncio.to_thread(read_fake_grok_seen, folder)
    argv = seen["argv"]
    assert argv[argv.index("--disallowed-tools") + 1].split(",") == list(DISALLOWED_GROK_TOOLS)
    assert "--no-subagents" in argv
    assert "--disable-web-search" in argv
    assert argv[argv.index("--rules") + 1] == "answer in Chinese"
    assert argv[-2:] == ["agent", "stdio"]
    assert seen["home"] == str(tmp_path / "grok-home")
    config_toml = (tmp_path / "grok-home" / ".grok" / "config.toml").read_text(encoding="utf-8")
    assert config_toml == GROK_PERMISSION_CONFIG
    new = next(r for r in seen["requests"] if r["method"] == "session/new")["params"]
    assert new["cwd"] == str(tmp_path)
    (server,) = new["mcpServers"]
    assert (server["type"], server["name"], server["url"]) == ("http", "arcreel", url)
    # 会话结束后令牌作废
    token = server["headers"][0]["value"].removeprefix("Bearer ")
    assert registry.get(token) is None


async def test_permission_is_granted_only_to_arcreel_tools(tool_server, tmp_path: Path) -> None:
    url, registry = tool_server
    folder = tmp_path / "fake"
    config, _ = _config(tmp_path, install_fake_grok(folder, permission=True), url, registry)
    async with GrokAgentClient(config) as client:
        await client.query(_one(_user("hi", "u-1")))
        await _until_idle(client)

    seen = await asyncio.to_thread(read_fake_grok_seen, folder)
    builtin, ours = seen["permission_answers"]
    assert builtin == {"outcome": {"outcome": "selected", "optionId": "no"}}
    assert ours == {"outcome": {"outcome": "selected", "optionId": "ok"}}


async def test_messages_during_a_prompt_are_queued_and_can_be_cancelled(tool_server, tmp_path: Path) -> None:
    url, registry = tool_server
    folder = tmp_path / "fake"
    config, _ = _config(tmp_path, install_fake_grok(folder, prompt_delay=0.6), url, registry)
    async with GrokAgentClient(config) as client:
        await client.query(_one(_user("first", "u-1")))
        await client.query(_one(_user("second", "u-2")))
        await client.query(_one(_user("third", "u-3")))
        assert await client.cancel_message("u-3") is True
        frames = await _until_idle(client)

    states = [(f.command_uuid, f.state) for f in frames if isinstance(f, CommandLifecycle)]
    assert states == [
        ("u-1", "started"),
        ("u-2", "queued"),
        ("u-3", "queued"),
        ("u-3", "cancelled"),
        ("u-1", "completed"),
        ("u-2", "started"),
        ("u-2", "completed"),
    ]
    seen = await asyncio.to_thread(read_fake_grok_seen, folder)
    prompts = [r["params"]["prompt"][0]["text"] for r in seen["requests"] if r["method"] == "session/prompt"]
    assert prompts == ["first", "second"]


async def test_interrupt_cancels_the_prompt(tool_server, tmp_path: Path) -> None:
    url, registry = tool_server
    folder = tmp_path / "fake"
    config, _ = _config(tmp_path, install_fake_grok(folder, prompt_delay=5), url, registry)
    async with GrokAgentClient(config) as client:
        await client.query(_one(_user("hi", "u-1")))
        await asyncio.sleep(0.3)
        await client.interrupt()
        frames = await _until_idle(client)

    result = next(f for f in frames if isinstance(f, ResultMessage))
    assert result.subtype == "interrupted"
    seen = await asyncio.to_thread(read_fake_grok_seen, folder)
    assert seen["notifications"] == [{"method": "session/cancel", "params": {"sessionId": "G1"}}]


async def test_a_failed_prompt_is_an_error_result(tool_server, tmp_path: Path) -> None:
    url, registry = tool_server
    config, _ = _config(tmp_path, install_fake_grok(tmp_path / "fake", fail=True), url, registry)
    async with GrokAgentClient(config) as client:
        await client.query(_one(_user("hi", "u-1")))
        frames = await _until_idle(client)

    result = next(f for f in frames if isinstance(f, ResultMessage))
    assert result.is_error is True
    assert result.errors == ["You have hit your usage limit"]


async def test_resuming_reopens_the_session(tool_server, tmp_path: Path) -> None:
    url, registry = tool_server
    folder = tmp_path / "fake"
    config, _ = _config(tmp_path, install_fake_grok(folder), url, registry, resume_session_id="G-old")
    async with GrokAgentClient(config) as client:
        assert client.session_id == "G-old"

    seen = await asyncio.to_thread(read_fake_grok_seen, folder)
    assert [r["method"] for r in seen["requests"] if r["method"].startswith("session/")] == ["session/resume"]


async def test_without_resume_support_history_replayed_by_load_is_not_repeated(tool_server, tmp_path: Path) -> None:
    url, registry = tool_server
    folder = tmp_path / "fake"
    config, _ = _config(tmp_path, install_fake_grok(folder, no_resume=True), url, registry, resume_session_id="G-old")
    async with GrokAgentClient(config) as client:
        await client.query(_one(_user("hi", "u-1")))
        frames = await _until_idle(client)

    texts = [b.text for f in frames if isinstance(f, AssistantMessage) for b in f.content if hasattr(b, "text")]
    assert "OLD HISTORY" not in "".join(texts)
    seen = await asyncio.to_thread(read_fake_grok_seen, folder)
    assert [r["method"] for r in seen["requests"] if r["method"].startswith("session/")][:2] == [
        "session/resume",
        "session/load",
    ]


async def test_an_api_key_connection_passes_the_key(tool_server, tmp_path: Path) -> None:
    url, registry = tool_server
    folder = tmp_path / "fake"
    config, _ = _config(tmp_path, install_fake_grok(folder), url, registry, api_key="xai-test")
    async with GrokAgentClient(config):
        pass

    seen = await asyncio.to_thread(read_fake_grok_seen, folder)
    assert seen["xai_key"] == "xai-test"
