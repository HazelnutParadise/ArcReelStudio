"""订阅额度的文字与图片后端：把请求交给各家的一轮执行器，结构化输出、看图、生图与错误都照契约上报。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from lib.backends.image_backends import codex as codex_image
from lib.backends.image_backends.base import ImageGenerationRequest, ImageOutputMissingError, ReferenceImage
from lib.backends.subscription_shared import SubscriptionCallError
from lib.backends.text_backends import subscription as text_sub
from lib.backends.text_backends.base import ImageInput, TextCapability, TextGenerationRequest
from lib.subscriptions.claude_turn import ClaudeTurnError, ClaudeTurnResult
from lib.subscriptions.codex_turn import CodexTurnError, CodexTurnResult
from lib.subscriptions.grok_turn import GrokTurnResult


class Answer(BaseModel):
    ok: bool


class Recorder:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[tuple, dict]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return self.result


async def test_claude_text_passes_schema_images_and_reports_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = Recorder(ClaudeTurnResult(text="", structured={"ok": True}, input_tokens=3, output_tokens=2, model="m-x"))
    monkeypatch.setattr(text_sub, "run_claude_turn", run)
    backend = text_sub.ClaudeSubscriptionTextBackend(oauth_token="tok", model="claude-sonnet-5-5")

    result = await backend.generate(
        TextGenerationRequest(prompt="p", response_schema=Answer, images=[ImageInput(path=tmp_path / "a.png")])
    )

    assert json.loads(result.text) == {"ok": True}
    assert (result.provider, result.model, result.input_tokens, result.output_tokens) == (
        "claude-subscription",
        "m-x",
        3,
        2,
    )
    args, kwargs = run.calls[0]
    assert args == ("tok", "p")
    assert kwargs["output_schema"]["properties"]["ok"]["type"] == "boolean"
    assert kwargs["input_images"] == [tmp_path / "a.png"]
    assert TextCapability.VISION in backend.capabilities


def test_claude_text_needs_a_token() -> None:
    with pytest.raises(SubscriptionCallError) as exc:
        text_sub.ClaudeSubscriptionTextBackend(oauth_token=None)
    assert exc.value.code == "auth_required"


async def test_turn_errors_become_non_retryable_subscription_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(text_sub, "run_claude_turn", Recorder(error=ClaudeTurnError("limit", code="usage_limit")))

    with pytest.raises(SubscriptionCallError) as exc:
        await text_sub.ClaudeSubscriptionTextBackend(oauth_token="t").generate(TextGenerationRequest(prompt="p"))

    assert (exc.value.code, exc.value.provider) == ("usage_limit", "claude-subscription")


async def test_chatgpt_text_strips_a_json_fence_for_structured_requests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = Recorder(CodexTurnResult(text='```json\n{"ok": true}\n```', input_tokens=9))
    monkeypatch.setattr(text_sub, "run_codex_turn", run)
    backend = text_sub.ChatGPTSubscriptionTextBackend(codex_home=tmp_path, model="gpt-5.5")

    result = await backend.generate(TextGenerationRequest(prompt="p", response_schema=Answer, system_prompt="s"))

    assert result.text == '{"ok": true}'
    args, kwargs = run.calls[0]
    assert args == (tmp_path, "p")
    assert kwargs["model"] == "gpt-5.5"
    assert kwargs["system_prompt"] == "s"


async def test_grok_text_puts_the_schema_in_the_prompt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run = Recorder(GrokTurnResult(text='{"ok": false}'))
    monkeypatch.setattr(text_sub, "run_grok_turn", run)
    backend = text_sub.GrokSubscriptionTextBackend(grok_home=tmp_path)

    result = await backend.generate(TextGenerationRequest(prompt="question", response_schema=Answer))

    assert result.text == '{"ok": false}'
    prompt = run.calls[0][0][1]
    assert prompt.startswith("question\n\n")
    assert '"ok"' in prompt


async def test_chatgpt_image_places_the_generated_image(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def make_image(folder: Path) -> Path:
        folder.mkdir(parents=True)
        made = folder / "codex-image-0.png"
        made.write_bytes(b"PNG")
        return made

    async def fake_turn(home: Path, instruction: str, *, input_images, image_output_dir: Path):
        made = await asyncio.to_thread(make_image, image_output_dir)
        fake_turn.seen = (instruction, list(input_images))  # type: ignore[attr-defined]  # 记下请求供断言
        return CodexTurnResult(text="", images=[made])

    monkeypatch.setattr(codex_image, "run_codex_turn", fake_turn)
    backend = codex_image.ChatGPTSubscriptionImageBackend(codex_home=tmp_path / "home")
    out = tmp_path / "shots" / "s1.png"

    result = await backend.generate(
        ImageGenerationRequest(
            prompt="a red fox", output_path=out, reference_images=[ReferenceImage(path=str(tmp_path / "ref.png"))]
        )
    )

    assert await asyncio.to_thread(out.read_bytes) == b"PNG"
    assert result.image_path == out
    instruction, refs = fake_turn.seen  # type: ignore[attr-defined]  # 上面记下的请求
    assert "a red fox" in instruction
    assert "9:16" in instruction
    assert refs == [tmp_path / "ref.png"]
    assert not await asyncio.to_thread((tmp_path / "shots" / ".s1-codex").exists)


async def test_chatgpt_image_without_output_is_an_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(codex_image, "run_codex_turn", Recorder(CodexTurnResult(text="no image")))
    backend = codex_image.ChatGPTSubscriptionImageBackend(codex_home=tmp_path)

    with pytest.raises(ImageOutputMissingError):
        await backend.generate(ImageGenerationRequest(prompt="x", output_path=tmp_path / "o.png"))


async def test_chatgpt_image_turn_errors_are_subscription_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(codex_image, "run_codex_turn", Recorder(error=CodexTurnError("x", code="auth_required")))
    backend = codex_image.ChatGPTSubscriptionImageBackend(codex_home=tmp_path)

    with pytest.raises(SubscriptionCallError) as exc:
        await backend.generate(ImageGenerationRequest(prompt="x", output_path=tmp_path / "o.png"))

    assert exc.value.code == "auth_required"
