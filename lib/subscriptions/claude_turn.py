"""用 Claude 订阅跑一次性的一轮文字：经 Agent SDK（内置的 Claude Code），只带订阅令牌。

订阅令牌只能经官方的 Claude Code 或 Agent SDK 使用，不能直接打 Messages API，所以文字生成也走 SDK：不读项目设置，
工作目录是临时目录。不看图时不给任何工具、只跑一轮；看图时把图片拷进工作目录，只开放 ``Read`` 工具读它们。结构化
输出用 SDK 的 ``output_format``。
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

from lib.config.env_keys import ANTHROPIC_ENV_KEYS
from lib.config.service import OAUTH_TOKEN_ENV_KEY

DEFAULT_TURN_TIMEOUT_SECONDS = 10 * 60.0
#: SDK 在助手消息上标出的错误类别 → 我们的错误码
_SDK_ERROR_CODES = {
    "rate_limit": "usage_limit",
    "billing_error": "usage_limit",
    "authentication_failed": "auth_required",
}

QueryFn = Callable[..., AsyncIterator[Any]]


class ClaudeTurnError(Exception):
    """这一轮没有完成。``code``：``usage_limit``、``auth_required``、``timeout``、``empty_output`` 或 ``None``。"""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class ClaudeTurnResult:
    text: str
    structured: Any = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    model: str | None = None


async def run_claude_turn(
    oauth_token: str,
    prompt: str,
    *,
    model: str | None = None,
    system_prompt: str | None = None,
    output_schema: Mapping[str, Any] | None = None,
    input_images: Sequence[Path] = (),
    query_fn: QueryFn = query,
    timeout: float = DEFAULT_TURN_TIMEOUT_SECONDS,  # noqa: ASYNC109 -- 一轮的等待上限，由 asyncio.wait_for 实现；仓库无 trio/anyio cancel scope
) -> ClaudeTurnResult:
    work_dir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="claude-turn-"))
    # 看图：把图片拷进工作目录，只开放 Read 工具让 Claude 读它们（读图要多一来一回，所以多给几轮）
    attached = await asyncio.to_thread(_copy_images, input_images, work_dir)
    if attached:
        listing = "\n".join(f"- ./{name}" for name in attached)
        prompt = f"{prompt}\n\nAttached images (read each with the Read tool before answering):\n{listing}"
    # 只带订阅令牌：API Key 凭证的地址、密钥与档位模型都清空，免得 CLI 读到容器里别的 Anthropic 设置
    env = dict.fromkeys(ANTHROPIC_ENV_KEYS, "")
    env[OAUTH_TOKEN_ENV_KEY] = oauth_token
    options = ClaudeAgentOptions(
        cwd=str(work_dir),
        tools=["Read"] if attached else [],
        allowed_tools=["Read"] if attached else [],
        max_turns=1 + 2 * len(attached) if attached else 1,
        setting_sources=[],
        model=model,
        system_prompt=system_prompt,
        env=env,
        output_format={"type": "json_schema", "schema": dict(output_schema)} if output_schema is not None else None,
    )
    try:
        return await asyncio.wait_for(_collect(query_fn(prompt=prompt, options=options)), timeout=timeout)
    except TimeoutError as exc:
        raise ClaudeTurnError("claude turn timed out", code="timeout") from exc
    finally:
        await asyncio.to_thread(shutil.rmtree, work_dir, True)  # hard-delete: temp -- 这一轮专用的临时工作目录


async def _collect(messages: AsyncIterator[Any]) -> ClaudeTurnResult:
    texts: list[str] = []
    result: ResultMessage | None = None
    sdk_error: str | None = None
    async for message in messages:
        if isinstance(message, AssistantMessage):
            sdk_error = message.error or sdk_error
            texts.extend(block.text for block in message.content if isinstance(block, TextBlock))
        elif isinstance(message, ResultMessage):
            result = message
    if sdk_error in _SDK_ERROR_CODES:
        raise ClaudeTurnError(f"claude subscription: {sdk_error}", code=_SDK_ERROR_CODES[sdk_error])
    if result is not None and result.is_error:
        detail = "; ".join(result.errors or []) or (result.result or result.subtype)
        raise ClaudeTurnError(detail, code=_error_code(detail))
    text = (result.result if result is not None and result.result else "") or "".join(texts)
    structured = result.structured_output if result is not None else None
    if structured is not None and not text:
        text = json.dumps(structured, ensure_ascii=False)
    if not text:
        raise ClaudeTurnError("claude returned no output", code="empty_output")
    usage = (result.usage if result is not None else None) or {}
    return ClaudeTurnResult(
        text=text,
        structured=structured,
        input_tokens=_int(usage.get("input_tokens")),
        output_tokens=_int(usage.get("output_tokens")),
        cache_read_tokens=_int(usage.get("cache_read_input_tokens")),
        model=next(iter(result.model_usage), None) if result is not None and result.model_usage else None,
    )


def _copy_images(images: Sequence[Path], work_dir: Path) -> list[str]:
    names: list[str] = []
    for index, source in enumerate(images, start=1):
        name = f"image-{index}{source.suffix or '.png'}"
        shutil.copyfile(source, work_dir / name)
        names.append(name)
    return names


def _int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _error_code(message: str) -> str | None:
    text = message.lower()
    if "limit" in text or "quota" in text or "rate" in text:
        return "usage_limit"
    if "auth" in text or "login" in text or "token" in text or "401" in text:
        return "auth_required"
    return None
