"""ChatGPT 订阅的一轮（经 Codex app-server）：用说同一套协议的假 app-server 走文字、结构化输出、生图与失败。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from lib.subscriptions.codex_turn import CodexTurnError, run_codex_turn

# 假 app-server：thread/start 记下参数，turn/start 后按旁边的 behaviour 文件回报项目与结果
_FAKE = f"""#!{sys.executable}
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
behaviour = json.load(open(os.path.join(here, "behaviour.json")))
seen = []
def send(o):
    sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()
cwd = None
for line in sys.stdin:
    m = json.loads(line); method, mid = m.get("method"), m.get("id")
    if method in ("thread/start", "turn/start"):
        seen.append({{"method": method, "params": m["params"]}})
        json.dump(seen, open(os.path.join(here, "seen.json"), "w"))
    if method == "initialize":
        send({{"id": mid, "result": {{}}}})
    elif method == "thread/start":
        cwd = m["params"]["cwd"]
        send({{"id": mid, "result": {{"thread": {{"id": "T1"}}}}}})
    elif method == "turn/start":
        send({{"id": mid, "result": {{"turn": {{"id": "U1"}}}}}})
        if behaviour.get("image"):
            path = os.path.join(cwd, "out.png"); open(path, "wb").write(b"PNG")
            send({{"method": "item/completed", "params": {{"threadId": "T1", "item": {{"type": "imageGeneration", "savedPath": path}}}}}})
        for text in behaviour.get("messages", []):
            send({{"method": "item/completed", "params": {{"threadId": "T1", "item": {{"type": "agentMessage", "text": text}}}}}})
        send({{"method": "thread/tokenUsage/updated", "params": {{"threadId": "T1", "tokenUsage": {{"last": {{"inputTokens": 12, "outputTokens": 5, "cachedInputTokens": 2}}}}}}}})
        status = behaviour.get("status", "completed")
        turn = {{"id": "U1", "status": status}}
        if status != "completed":
            turn["error"] = {{"message": behaviour.get("error", "boom"), "codexErrorInfo": behaviour.get("info")}}
        send({{"method": "turn/completed", "params": {{"threadId": "T1", "turn": turn}}}})
    elif mid is not None:
        send({{"id": mid, "result": {{}}}})
"""


@pytest.fixture
def fake(tmp_path: Path):
    folder = tmp_path / "fake"
    folder.mkdir()
    cli = folder / "codex"
    cli.write_text(_FAKE, encoding="utf-8")
    cli.chmod(0o755)

    def configure(**behaviour) -> str:
        (folder / "behaviour.json").write_text(json.dumps(behaviour), encoding="utf-8")
        return str(cli)

    def seen() -> list[dict]:
        return json.loads((folder / "seen.json").read_text(encoding="utf-8"))

    configure.seen = seen  # type: ignore[attr-defined]  # 让用例读假 app-server 记下的请求
    return configure


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """连线专属的 HOME（真连线一定有这个目录）"""
    folder = tmp_path / "home"
    folder.mkdir()
    return folder


async def test_returns_the_final_message_and_usage(fake, home: Path, tmp_path: Path) -> None:
    cli = fake(messages=["thinking…", "final answer"])

    result = await run_codex_turn(home, "hello", model="gpt-5.5", system_prompt="be brief", cli_path=cli)

    assert result.text == "final answer"
    assert (result.input_tokens, result.output_tokens, result.cached_input_tokens) == (12, 5, 2)
    thread, turn = fake.seen()
    assert thread["params"]["model"] == "gpt-5.5"
    assert thread["params"]["developerInstructions"] == "be brief"
    assert thread["params"]["sandbox"] == "read-only"
    assert thread["params"]["approvalPolicy"] == "never"
    assert thread["params"]["ephemeral"] is True
    assert turn["params"]["input"][0] == {"type": "text", "text": "hello", "text_elements": []}


async def test_passes_the_output_schema_and_input_images(fake, home: Path, tmp_path: Path) -> None:
    cli = fake(messages=['{"ok": true}'])
    picture = tmp_path / "in.png"
    picture.write_bytes(b"x")

    await run_codex_turn(home, "describe", output_schema={"type": "object"}, input_images=[picture], cli_path=cli)

    turn = fake.seen()[1]["params"]
    assert turn["outputSchema"] == {"type": "object"}
    assert turn["input"][1] == {"type": "localImage", "path": str(picture)}


async def test_generated_images_are_copied_out_of_the_temporary_folder(fake, home: Path, tmp_path: Path) -> None:
    cli = fake(image=True)

    result = await run_codex_turn(home, "draw a cat", image_output_dir=tmp_path / "out", cli_path=cli)

    assert [p.read_bytes() for p in result.images] == [b"PNG"]
    assert result.images[0].parent == tmp_path / "out"


async def test_a_failed_turn_reports_a_usage_limit(fake, home: Path, tmp_path: Path) -> None:
    cli = fake(status="failed", error="You've hit your usage limit", info="usageLimitExceeded")

    with pytest.raises(CodexTurnError) as exc:
        await run_codex_turn(home, "hello", cli_path=cli)

    assert exc.value.code == "usage_limit"


async def test_a_turn_without_output_is_an_error(fake, home: Path, tmp_path: Path) -> None:
    cli = fake(messages=[])

    with pytest.raises(CodexTurnError) as exc:
        await run_codex_turn(home, "hello", cli_path=cli)

    assert exc.value.code == "empty_output"


async def test_a_missing_cli_is_reported(home: Path, tmp_path: Path) -> None:
    with pytest.raises(CodexTurnError) as exc:
        await run_codex_turn(home, "hello", cli_path=str(tmp_path / "missing"))

    assert exc.value.code == "cli_unavailable"
