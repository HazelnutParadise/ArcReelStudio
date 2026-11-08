"""Codex 引擎 client：用说同一套协定的假 app-server，确认它吐出的帧都能被 SDK 解析、排队与中断语意与 Claude 引擎一致。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, UserMessage

from server.agent_runtime import sdk_frames
from server.agent_runtime.codex_client import CodexAgentClient, CodexSessionConfig
from server.agent_runtime.sdk_frames import CommandLifecycle
from tests.codex_fakes import install_fake_codex, read_fake_codex_seen


@pytest.fixture
def fake_app_server(tmp_path: Path):
    folder = tmp_path / "fake-codex"

    def configure(**behaviour: Any) -> str:
        return install_fake_codex(folder, **behaviour)

    configure.seen = lambda: read_fake_codex_seen(folder)  # type: ignore[attr-defined]  # 让用例读假 app-server 记下的请求
    return configure


def _config_and_calls(tmp_path: Path, cli: str, **overrides: Any) -> tuple[CodexSessionConfig, list[tuple[str, Any]]]:
    calls: list[tuple[str, Any]] = []

    async def caller(tool: str, arguments: Any) -> dict[str, Any]:
        calls.append((tool, arguments))
        return {"contentItems": [{"type": "inputText", "text": "projects: demo"}], "success": True}

    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    fields: dict[str, Any] = {
        "codex_home": home,
        "project_cwd": tmp_path,
        "model": "gpt-5.5",
        "developer_instructions": "answer in Chinese",
        "tool_specs": [{"type": "function", "name": "list_projects", "description": "d", "inputSchema": {}}],
        "tool_callers": {"list_projects": caller},
        "arcreel_tool_names": frozenset({"list_projects"}),
        "cli_path": cli,
    }
    fields.update(overrides)
    return CodexSessionConfig(**fields), calls


def _config(tmp_path: Path, cli: str, **overrides: Any) -> CodexSessionConfig:
    return _config_and_calls(tmp_path, cli, **overrides)[0]


async def _one(message: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    yield message


def _user(text: str, uid: str) -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": text}, "uuid": uid, "session_id": ""}


async def _collect_until_idle(client: CodexAgentClient, *, idles: int = 1) -> list[Any]:
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

    await asyncio.wait_for(run(), timeout=15)
    return parsed


async def test_a_turn_becomes_sdk_frames_with_tool_round_trip_and_usage(fake_app_server, tmp_path: Path) -> None:
    config, calls = _config_and_calls(tmp_path, fake_app_server(tool=True))
    async with CodexAgentClient(config) as client:
        await client.query(_one(_user("hi", "u-1")))
        frames = await _collect_until_idle(client)

    kinds = [type(f).__name__ if not isinstance(f, CommandLifecycle) else f"lifecycle:{f.state}" for f in frames]
    assert isinstance(frames[0], SystemMessage)
    assert frames[0].subtype == "init"
    assert frames[0].data["session_id"] == "T1"
    assert "lifecycle:started" in kinds
    assert "lifecycle:completed" in kinds
    tool_use = next(
        f
        for f in frames
        if isinstance(f, AssistantMessage) and f.content and f.content[0].__class__.__name__ == "ToolUseBlock"
    )
    assert tool_use.content[0].name == "mcp__arcreel__list_projects"
    assert tool_use.content[0].input == {"x": 1}
    tool_result = next(f for f in frames if isinstance(f, UserMessage))
    assert tool_result.content[0].content == "projects: demo"
    assert calls == [("list_projects", {"x": 1})]
    reply = next(
        f for f in frames if isinstance(f, AssistantMessage) and f.content and getattr(f.content[0], "text", None)
    )
    assert reply.content[0].text == "done U1"
    assert reply.model == "gpt-5.5"
    result = next(f for f in frames if isinstance(f, ResultMessage))
    assert (result.subtype, result.is_error, result.result) == ("success", False, "done U1")
    assert result.model_usage == {
        "gpt-5.5": {"inputTokens": 60, "cacheReadInputTokens": 40, "cacheCreationInputTokens": 0, "outputTokens": 7}
    }


async def test_codex_is_started_without_its_own_tools_and_with_project_settings(
    fake_app_server, tmp_path: Path
) -> None:
    config = _config(tmp_path, fake_app_server(), skill_roots=(tmp_path / ".claude" / "skills",))
    async with CodexAgentClient(config):
        pass

    seen = await asyncio.to_thread(fake_app_server.seen)
    argv = " ".join(seen["argv"])
    for feature in ("shell_tool", "unified_exec", "multi_agent", "view_image", "image_generation"):
        assert f"features.{feature}=false" in argv
    assert 'project_doc_fallback_filenames=["CLAUDE.md"]' in argv
    start = next(r for r in seen["requests"] if r["method"] == "thread/start")["params"]
    assert start["cwd"] == str(tmp_path)
    assert (start["sandbox"], start["approvalPolicy"]) == ("read-only", "never")
    assert start["developerInstructions"] == "answer in Chinese"
    assert [t["name"] for t in start["dynamicTools"]] == ["list_projects"]
    roots = next(r for r in seen["requests"] if r["method"] == "skills/extraRoots/set")["params"]
    assert roots == {"extraRoots": [str(tmp_path / ".claude" / "skills")]}


async def test_messages_during_a_turn_are_queued_and_can_be_cancelled(fake_app_server, tmp_path: Path) -> None:
    config = _config(tmp_path, fake_app_server(turn_delay=0.6))
    async with CodexAgentClient(config) as client:
        await client.query(_one(_user("first", "u-1")))
        await client.query(_one(_user("second", "u-2")))
        await client.query(_one(_user("third", "u-3")))
        assert await client.cancel_message("u-3") is True
        assert await client.cancel_message("nope") is False
        frames = await _collect_until_idle(client)

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
    seen = await asyncio.to_thread(fake_app_server.seen)
    turns = [r["params"]["input"][0]["text"] for r in seen["requests"] if r["method"] == "turn/start"]
    assert turns == ["first", "second"]


async def test_interrupt_names_the_active_turn(fake_app_server, tmp_path: Path) -> None:
    config = _config(tmp_path, fake_app_server(turn_delay=0.5))
    async with CodexAgentClient(config) as client:
        await client.query(_one(_user("hi", "u-1")))
        await client.interrupt()
        await _collect_until_idle(client)

    seen = await asyncio.to_thread(fake_app_server.seen)
    interrupt = next(r for r in seen["requests"] if r["method"] == "turn/interrupt")["params"]
    assert interrupt == {"threadId": "T1", "turnId": "U1"}


async def test_resuming_reopens_the_same_thread(fake_app_server, tmp_path: Path) -> None:
    config = _config(tmp_path, fake_app_server(), resume_thread_id="T-old")
    async with CodexAgentClient(config) as client:
        assert client.thread_id == "T-old"

    seen = await asyncio.to_thread(fake_app_server.seen)
    assert [r["method"] for r in seen["requests"] if r["method"].startswith("thread/")] == ["thread/resume"]


async def test_a_failed_turn_is_an_error_result_with_its_kind(fake_app_server, tmp_path: Path) -> None:
    config = _config(tmp_path, fake_app_server(status="failed"))
    async with CodexAgentClient(config) as client:
        await client.query(_one(_user("hi", "u-1")))
        frames = await _collect_until_idle(client)

    result = next(f for f in frames if isinstance(f, ResultMessage))
    assert result.is_error is True
    assert result.subtype == "error_during_execution"
    assert result.errors == ["You've hit your usage limit"]


async def test_other_server_requests_are_refused(fake_app_server, tmp_path: Path) -> None:
    config = _config(tmp_path, fake_app_server(approval=True))
    async with CodexAgentClient(config) as client:
        await client.query(_one(_user("hi", "u-1")))
        await _collect_until_idle(client)

    seen = await asyncio.to_thread(fake_app_server.seen)
    reply = next(r for r in seen["replies"] if r.get("id") == 901)
    assert "error" in reply


async def test_image_blocks_are_sent_as_local_images(fake_app_server, tmp_path: Path) -> None:
    config = _config(tmp_path, fake_app_server())
    message = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "UE5H"}},
            ],
        },
        "uuid": "u-1",
    }
    async with CodexAgentClient(config) as client:
        await client.query(_one(message))
        await _collect_until_idle(client)

    seen = await asyncio.to_thread(fake_app_server.seen)
    inputs = next(r for r in seen["requests"] if r["method"] == "turn/start")["params"]["input"]
    assert inputs[0]["text"] == "look"
    assert inputs[1]["type"] == "localImage"
    assert not await asyncio.to_thread(Path(inputs[1]["path"]).exists)
