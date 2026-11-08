"""Claude 订阅的一轮（经 Agent SDK）：只带订阅令牌、不给工具、一轮就停；结果、结构化输出与错误归类。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from lib.subscriptions.claude_turn import ClaudeTurnError, run_claude_turn


def _result(**overrides: Any) -> ResultMessage:
    fields: dict[str, Any] = {
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 1,
        "session_id": "s",
        "result": "final text",
        "usage": {"input_tokens": 10, "output_tokens": 4, "cache_read_input_tokens": 3},
        "model_usage": {"claude-sonnet-5-5": {}},
    }
    fields.update(overrides)
    return ResultMessage(**fields)


class FakeQuery:
    def __init__(self, *messages: Any) -> None:
        self.messages = messages
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *, prompt: str, options: Any) -> AsyncIterator[Any]:
        self.calls.append({"prompt": prompt, "options": options})

        async def gen() -> AsyncIterator[Any]:
            for message in self.messages:
                yield message

        return gen()


async def test_runs_one_toolless_turn_with_only_the_subscription_token() -> None:
    fake = FakeQuery(AssistantMessage(content=[TextBlock(text="draft")], model="m"), _result())

    result = await run_claude_turn(
        "sk-ant-oat01-x", "hello", model="claude-sonnet-5-5", system_prompt="be brief", query_fn=fake
    )

    assert result.text == "final text"
    assert (result.input_tokens, result.output_tokens, result.cache_read_tokens) == (10, 4, 3)
    assert result.model == "claude-sonnet-5-5"
    options = fake.calls[0]["options"]
    assert fake.calls[0]["prompt"] == "hello"
    assert options.tools == []
    assert options.max_turns == 1
    assert options.setting_sources == []
    assert options.model == "claude-sonnet-5-5"
    assert options.system_prompt == "be brief"
    assert options.env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-x"
    assert options.env["ANTHROPIC_API_KEY"] == ""
    assert options.output_format is None


async def test_structured_output_uses_the_sdk_output_format() -> None:
    fake = FakeQuery(_result(result=None, structured_output={"ok": True}))

    result = await run_claude_turn("t", "x", output_schema={"type": "object"}, query_fn=fake)

    assert result.structured == {"ok": True}
    assert result.text == '{"ok": true}'
    assert fake.calls[0]["options"].output_format == {"type": "json_schema", "schema": {"type": "object"}}


async def test_falls_back_to_the_assistant_text_without_a_result() -> None:
    fake = FakeQuery(AssistantMessage(content=[TextBlock(text="a"), TextBlock(text="b")], model="m"))

    assert (await run_claude_turn("t", "x", query_fn=fake)).text == "ab"


@pytest.mark.parametrize(("error", "code"), [("rate_limit", "usage_limit"), ("authentication_failed", "auth_required")])
async def test_sdk_error_kinds_are_classified(error: str, code: str) -> None:
    fake = FakeQuery(AssistantMessage(content=[], model="m", error=error), _result(is_error=True, result=None))

    with pytest.raises(ClaudeTurnError) as exc:
        await run_claude_turn("t", "x", query_fn=fake)

    assert exc.value.code == code


async def test_an_error_result_is_reported() -> None:
    fake = FakeQuery(_result(is_error=True, result=None, errors=["You've hit your usage limit"]))

    with pytest.raises(ClaudeTurnError) as exc:
        await run_claude_turn("t", "x", query_fn=fake)

    assert exc.value.code == "usage_limit"


async def test_no_output_is_an_error() -> None:
    with pytest.raises(ClaudeTurnError) as exc:
        await run_claude_turn("t", "x", query_fn=FakeQuery(_result(result=None)))

    assert exc.value.code == "empty_output"


async def test_images_are_copied_in_and_only_the_read_tool_is_allowed(tmp_path) -> None:
    picture = tmp_path / "ref.jpg"
    picture.write_bytes(b"jpg")
    seen: dict[str, object] = {}

    class Capture(FakeQuery):
        def __call__(self, *, prompt: str, options):
            seen["copied"] = (Path(options.cwd) / "image-1.jpg").read_bytes()
            return super().__call__(prompt=prompt, options=options)

    fake = Capture(_result())
    await run_claude_turn("t", "describe", input_images=[picture], query_fn=fake)

    options = fake.calls[0]["options"]
    assert options.tools == ["Read"]
    assert options.allowed_tools == ["Read"]
    assert options.max_turns == 3
    assert "./image-1.jpg" in fake.calls[0]["prompt"]
    assert seen["copied"] == b"jpg"
