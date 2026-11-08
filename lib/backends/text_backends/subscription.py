"""订阅额度的文字后端：Claude（经 Agent SDK）、ChatGPT（经 Codex app-server）、Grok（经 Grok CLI 的 ACP）。

订阅只能经各家官方客户端使用，所以每次调用都起一次官方 CLI 跑一轮（见 ``lib.subscriptions.*_turn``）。用订阅额度不按
token 计价（供应商倍率为 0），用量照实上报。额度用完或要重新登录时抛 :class:`SubscriptionCallError`，不重试。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from lib.backends.subscription_shared import (
    PROVIDER_CHATGPT_SUBSCRIPTION,
    PROVIDER_CLAUDE_SUBSCRIPTION,
    PROVIDER_GROK_SUBSCRIPTION,
    SubscriptionCallError,
)
from lib.backends.text_backends.base import (
    TextCapability,
    TextGenerationRequest,
    TextGenerationResult,
    resolve_schema,
    strip_json_code_fence,
)
from lib.subscriptions.claude_turn import ClaudeTurnError, run_claude_turn
from lib.subscriptions.codex_turn import CodexTurnError, run_codex_turn
from lib.subscriptions.grok_turn import GrokTurnError, run_grok_turn


def _schema_of(request: TextGenerationRequest) -> dict[str, Any] | None:
    schema = request.response_schema
    if schema is None:
        return None
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return resolve_schema(schema)
    return resolve_schema(schema) if isinstance(schema, dict) else None


def _image_paths(request: TextGenerationRequest) -> list[Path]:
    """看图任务的本地图片；只有网址的图片订阅 CLI 拿不到，略过。"""
    return [Path(img.path) for img in request.images or [] if img.path is not None]


def _schema_instruction(schema: dict[str, Any]) -> str:
    return (
        "Reply with a single JSON object that conforms to this JSON Schema, and nothing else "
        "(no prose, no code fence):\n" + json.dumps(schema, ensure_ascii=False)
    )


class ClaudeSubscriptionTextBackend:
    """用 Claude 订阅生成文字，可以看图。"""

    def __init__(self, *, oauth_token: str | None, model: str | None = None) -> None:
        if not oauth_token:
            raise SubscriptionCallError(
                "Claude subscription connection has no token",
                provider=PROVIDER_CLAUDE_SUBSCRIPTION,
                code="auth_required",
            )
        self._token = oauth_token
        self._model = model or "claude-sonnet-5-5"

    @property
    def name(self) -> str:
        return PROVIDER_CLAUDE_SUBSCRIPTION

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[TextCapability]:
        return {TextCapability.TEXT_GENERATION, TextCapability.STRUCTURED_OUTPUT, TextCapability.VISION}

    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        try:
            turn = await run_claude_turn(
                self._token,
                request.prompt,
                model=self._model,
                system_prompt=request.system_prompt,
                output_schema=_schema_of(request),
                input_images=_image_paths(request),
            )
        except ClaudeTurnError as exc:
            raise SubscriptionCallError(str(exc), provider=self.name, code=exc.code) from exc
        text = json.dumps(turn.structured, ensure_ascii=False) if turn.structured is not None else turn.text
        return TextGenerationResult(
            text=text,
            provider=self.name,
            model=turn.model or self._model,
            input_tokens=turn.input_tokens,
            output_tokens=turn.output_tokens,
            cache_read_tokens=turn.cache_read_tokens,
        )


class ChatGPTSubscriptionTextBackend:
    """用 ChatGPT 订阅（经 Codex）生成文字，可以看图。"""

    def __init__(self, *, codex_home: Path, model: str | None = None) -> None:
        self._home = codex_home
        self._model = model or "gpt-5.5"

    @property
    def name(self) -> str:
        return PROVIDER_CHATGPT_SUBSCRIPTION

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[TextCapability]:
        return {TextCapability.TEXT_GENERATION, TextCapability.STRUCTURED_OUTPUT, TextCapability.VISION}

    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        images = _image_paths(request)
        try:
            turn = await run_codex_turn(
                self._home,
                request.prompt,
                model=self._model,
                system_prompt=request.system_prompt,
                output_schema=_schema_of(request),
                input_images=images,
            )
        except CodexTurnError as exc:
            raise SubscriptionCallError(str(exc), provider=self.name, code=exc.code) from exc
        return TextGenerationResult(
            text=strip_json_code_fence(turn.text) if request.response_schema is not None else turn.text,
            provider=self.name,
            model=self._model,
            input_tokens=turn.input_tokens,
            output_tokens=turn.output_tokens,
            cache_read_tokens=turn.cached_input_tokens,
        )


class GrokSubscriptionTextBackend:
    """用 Grok 订阅（经 Grok CLI）生成文字，可以看图。结构化输出靠在提示里附上 JSON Schema。"""

    def __init__(self, *, grok_home: Path, model: str | None = None) -> None:
        self._home = grok_home
        self._model = model or "grok-build"

    @property
    def name(self) -> str:
        return PROVIDER_GROK_SUBSCRIPTION

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[TextCapability]:
        return {TextCapability.TEXT_GENERATION, TextCapability.STRUCTURED_OUTPUT, TextCapability.VISION}

    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        schema = _schema_of(request)
        prompt = request.prompt if schema is None else f"{request.prompt}\n\n{_schema_instruction(schema)}"
        try:
            turn = await run_grok_turn(
                self._home,
                prompt,
                model=self._model,
                system_prompt=request.system_prompt,
                input_images=_image_paths(request),
            )
        except GrokTurnError as exc:
            raise SubscriptionCallError(str(exc), provider=self.name, code=exc.code) from exc
        text = strip_json_code_fence(turn.text) if schema is not None else turn.text
        return TextGenerationResult(text=text, provider=self.name, model=self._model)
