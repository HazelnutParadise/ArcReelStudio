"""Grok 订阅的一轮（经 ``grok agent stdio``，ACP JSON-RPC 2.0）：用说同一套协议的假 CLI 走文字、拒绝服务器请求与失败。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from lib.subscriptions.grok_turn import GrokTurnError, run_grok_turn

# 假 grok CLI：从自己所在目录读 behaviour.json，把收到的请求与自身启动信息写进同目录的 seen.json。
# 不靠环境变量找文件——run_grok_turn 只带 HOME/PATH/LANG，看不到测试进程设的任何变量。
_FAKE_GROK_SCRIPT = r'''
import json, os, sys, time

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "behaviour.json"), encoding="utf-8") as handle:
    behaviour = json.load(handle)

seen = {
    "argv": sys.argv[1:],
    "home": os.environ.get("HOME"),
    "has_marker": "MARKER" in os.environ,
    "pid": os.getpid(),
    "cwd": None,
    "cwd_exists": None,
    "requests": [],
    "server_request_reply": None,
}


def dump():
    with open(os.path.join(here, "seen.json"), "w", encoding="utf-8") as handle:
        json.dump(seen, handle)


def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


dump()

while True:
    line = sys.stdin.readline()
    if not line:
        break
    message = json.loads(line)
    method = message.get("method")
    message_id = message.get("id")

    if method is None:
        if message_id == 9001 and "error" in message:
            seen["server_request_reply"] = message
            dump()
        continue

    seen["requests"].append({"method": method, "params": message.get("params")})
    dump()

    if method == "initialize":
        send({"jsonrpc": "2.0", "id": message_id, "result": {"protocolVersion": 1, "agentCapabilities": {}}})
    elif method == "session/new":
        cwd = message.get("params", {}).get("cwd")
        seen["cwd"] = cwd
        seen["cwd_exists"] = bool(cwd) and os.path.isdir(cwd)
        dump()
        send({"jsonrpc": "2.0", "id": message_id, "result": {"sessionId": "S1"}})
    elif method == "session/prompt":
        if behaviour.get("hang"):
            time.sleep(3600)
        if behaviour.get("request_permission"):
            send({
                "jsonrpc": "2.0",
                "id": 9001,
                "method": "session/request_permission",
                "params": {"sessionId": "S1", "toolCall": {}},
            })
            while True:
                reply_line = sys.stdin.readline()
                if not reply_line:
                    break
                reply = json.loads(reply_line)
                if reply.get("id") == 9001:
                    seen["server_request_reply"] = reply
                    dump()
                    break
        for chunk in behaviour.get("chunks", []):
            send({
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": "S1",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": chunk},
                    },
                },
            })
        error = behaviour.get("prompt_error")
        if error:
            send({"jsonrpc": "2.0", "id": message_id, "error": {"code": error.get("code", -32000), "message": error["message"]}})
        else:
            send({"jsonrpc": "2.0", "id": message_id, "result": {"stopReason": behaviour.get("stop_reason", "end_turn")}})
'''

_FAKE_GROK = f"#!{sys.executable}\n" + _FAKE_GROK_SCRIPT


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@pytest.fixture
def fake_grok_cli(tmp_path: Path):
    folder = tmp_path / "fake-grok"
    folder.mkdir()
    cli = folder / "grok"
    cli.write_text(_FAKE_GROK, encoding="utf-8")
    cli.chmod(0o755)

    def configure(**behaviour) -> str:
        (folder / "behaviour.json").write_text(json.dumps(behaviour), encoding="utf-8")
        return str(cli)

    def seen() -> dict:
        return json.loads((folder / "seen.json").read_text(encoding="utf-8"))

    configure.seen = seen  # type: ignore[attr-defined]  # 让用例读假 CLI 记下的启动信息与请求
    return configure


@pytest.fixture
def grok_home_dir(tmp_path: Path) -> Path:
    """连线专属的 HOME（真连线一定有这个目录）"""
    folder = tmp_path / "grok-home"
    folder.mkdir()
    return folder


async def test_collects_every_chunk_in_order_and_reports_end_turn(fake_grok_cli, grok_home_dir: Path) -> None:
    cli = fake_grok_cli(chunks=["Hel", "lo", " world"])

    result = await run_grok_turn(grok_home_dir, "hi", cli_path=cli)

    assert result.text == "Hello world"
    assert result.stop_reason == "end_turn"
    seen = await asyncio.to_thread(fake_grok_cli.seen)
    prompt_request = next(r for r in seen["requests"] if r["method"] == "session/prompt")
    assert prompt_request["params"]["prompt"] == [{"type": "text", "text": "hi"}]


async def test_launches_the_cli_with_an_isolated_environment(
    fake_grok_cli, grok_home_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MARKER", "leaked-from-the-test-process")
    cli = fake_grok_cli(chunks=["ok"])

    await run_grok_turn(grok_home_dir, "hi", cli_path=cli)

    seen = await asyncio.to_thread(fake_grok_cli.seen)
    assert "--no-auto-update" in seen["argv"]
    assert seen["argv"][-2:] == ["agent", "stdio"]
    assert "-m" not in seen["argv"]
    assert seen["home"] == str(grok_home_dir)
    assert seen["has_marker"] is False


async def test_passes_the_model_to_the_cli(fake_grok_cli, grok_home_dir: Path) -> None:
    cli = fake_grok_cli(chunks=["ok"])

    await run_grok_turn(grok_home_dir, "hi", model="grok-4", cli_path=cli)

    seen = await asyncio.to_thread(fake_grok_cli.seen)
    argv = seen["argv"]
    assert argv[argv.index("-m") + 1] == "grok-4"


async def test_session_new_uses_a_live_temporary_directory_and_no_mcp_servers(
    fake_grok_cli, grok_home_dir: Path
) -> None:
    cli = fake_grok_cli(chunks=["ok"])

    await run_grok_turn(grok_home_dir, "hi", cli_path=cli)

    seen = await asyncio.to_thread(fake_grok_cli.seen)
    initialize = next(r for r in seen["requests"] if r["method"] == "initialize")
    assert initialize["params"]["protocolVersion"] == 1
    assert initialize["params"]["clientCapabilities"] == {}
    session_new = next(r for r in seen["requests"] if r["method"] == "session/new")
    assert session_new["params"]["mcpServers"] == []
    assert seen["cwd_exists"] is True
    assert Path(seen["cwd"]) != grok_home_dir
    assert grok_home_dir not in Path(seen["cwd"]).parents


async def test_system_prompt_precedes_the_prompt_with_a_blank_line(fake_grok_cli, grok_home_dir: Path) -> None:
    cli = fake_grok_cli(chunks=["ok"])

    await run_grok_turn(grok_home_dir, "hello", system_prompt="be brief", cli_path=cli)

    seen = await asyncio.to_thread(fake_grok_cli.seen)
    prompt_request = next(r for r in seen["requests"] if r["method"] == "session/prompt")
    assert prompt_request["params"]["prompt"] == [{"type": "text", "text": "be brief\n\nhello"}]


async def test_refuses_server_requests_with_method_not_found(fake_grok_cli, grok_home_dir: Path) -> None:
    cli = fake_grok_cli(chunks=["ok"], request_permission=True)

    await run_grok_turn(grok_home_dir, "hi", cli_path=cli, timeout=10)

    seen = await asyncio.to_thread(fake_grok_cli.seen)
    reply = seen["server_request_reply"]
    assert reply["id"] == 9001
    assert reply["error"]["code"] == -32601


async def test_an_unauthenticated_prompt_is_reported_as_auth_required(fake_grok_cli, grok_home_dir: Path) -> None:
    cli = fake_grok_cli(prompt_error={"code": -32000, "message": "Not signed in"})

    with pytest.raises(GrokTurnError) as exc:
        await run_grok_turn(grok_home_dir, "hi", cli_path=cli)

    assert exc.value.code == "auth_required"


async def test_a_prompt_over_the_usage_limit_is_reported(fake_grok_cli, grok_home_dir: Path) -> None:
    cli = fake_grok_cli(prompt_error={"code": -32000, "message": "You have hit your usage limit"})

    with pytest.raises(GrokTurnError) as exc:
        await run_grok_turn(grok_home_dir, "hi", cli_path=cli)

    assert exc.value.code == "usage_limit"


async def test_a_turn_without_chunks_is_an_empty_output_error(fake_grok_cli, grok_home_dir: Path) -> None:
    cli = fake_grok_cli(chunks=[])

    with pytest.raises(GrokTurnError) as exc:
        await run_grok_turn(grok_home_dir, "hi", cli_path=cli)

    assert exc.value.code == "empty_output"


async def test_a_silent_cli_times_out_and_the_child_is_gone(fake_grok_cli, grok_home_dir: Path) -> None:
    cli = fake_grok_cli(hang=True)

    with pytest.raises(GrokTurnError) as exc:
        await run_grok_turn(grok_home_dir, "hi", cli_path=cli, timeout=0.5)

    assert exc.value.code == "timeout"
    seen = await asyncio.to_thread(fake_grok_cli.seen)
    for _ in range(100):
        if not await asyncio.to_thread(_pid_alive, seen["pid"]):
            break
        await asyncio.sleep(0.05)
    assert not await asyncio.to_thread(_pid_alive, seen["pid"])
    assert not await asyncio.to_thread(Path(seen["cwd"]).exists)


async def test_a_missing_cli_is_reported(grok_home_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(GrokTurnError) as exc:
        await run_grok_turn(grok_home_dir, "hi", cli_path=str(tmp_path / "missing-grok"))

    assert exc.value.code == "cli_unavailable"


async def test_the_temporary_working_directory_is_removed_afterwards(fake_grok_cli, grok_home_dir: Path) -> None:
    cli = fake_grok_cli(chunks=["ok"])

    await run_grok_turn(grok_home_dir, "hi", cli_path=cli)

    seen = await asyncio.to_thread(fake_grok_cli.seen)
    assert seen["cwd_exists"] is True
    assert not await asyncio.to_thread(Path(seen["cwd"]).exists)
