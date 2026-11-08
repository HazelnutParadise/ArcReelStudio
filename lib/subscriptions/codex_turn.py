"""用 ChatGPT 订阅（经 Codex）跑一次性的一轮：文字、结构化输出、看图，以及 Codex 内置的生图。

每次调用起一个 ``codex app-server``，以连线专属的 HOME 为 ``CODEX_HOME``（凭证在那里由 Codex 原地续期），开一个
不落盘的会话、只读沙箱、不请求批准，跑完这一轮就结束进程。工作目录是临时目录，生图结果从中拷出后删除。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib.agent.codex_app_server import CodexAppServer, CodexRpcError

#: 一轮最长等多久（生图比一般回合慢好几倍）
DEFAULT_TURN_TIMEOUT_SECONDS = 15 * 60.0


class CodexTurnError(Exception):
    """这一轮没有完成：Codex 报错、额度用完、超时或没有产出。"""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class CodexTurnResult:
    text: str
    #: 生图结果，已拷到调用方指定的目录
    images: list[Path] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None


async def run_codex_turn(
    codex_home: Path,
    prompt: str,
    *,
    model: str | None = None,
    system_prompt: str | None = None,
    output_schema: Mapping[str, Any] | None = None,
    input_images: Sequence[Path] = (),
    image_output_dir: Path | None = None,
    cli_path: str | None = None,
    timeout: float = DEFAULT_TURN_TIMEOUT_SECONDS,  # noqa: ASYNC109 -- 一轮的等待上限，由 asyncio.wait_for 实现；仓库无 trio/anyio cancel scope
) -> CodexTurnResult:
    """跑一轮并返回最后的回复文字与生成的图片。"""
    work_dir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="codex-turn-"))
    try:
        server = await CodexAppServer.start(str(codex_home), cli_path=cli_path)
    except CodexRpcError as exc:
        await asyncio.to_thread(shutil.rmtree, work_dir, True)  # hard-delete: temp -- 起不了进程，删掉刚建的临时工作目录
        raise CodexTurnError(str(exc), code="cli_unavailable") from exc
    try:
        return await asyncio.wait_for(
            _run(server, work_dir, prompt, model, system_prompt, output_schema, input_images, image_output_dir),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise CodexTurnError("codex turn timed out", code="timeout") from exc
    finally:
        await server.close()
        await asyncio.to_thread(shutil.rmtree, work_dir, True)  # hard-delete: temp -- 这一轮专用的临时工作目录


async def _run(
    server: CodexAppServer,
    work_dir: Path,
    prompt: str,
    model: str | None,
    system_prompt: str | None,
    output_schema: Mapping[str, Any] | None,
    input_images: Sequence[Path],
    image_output_dir: Path | None,
) -> CodexTurnResult:
    thread_params: dict[str, Any] = {
        "cwd": str(work_dir),
        "sandbox": "read-only",
        "approvalPolicy": "never",
        "ephemeral": True,
    }
    if model:
        thread_params["model"] = model
    if system_prompt:
        thread_params["developerInstructions"] = system_prompt
    try:
        started = await server.request("thread/start", thread_params)
    except CodexRpcError as exc:
        raise CodexTurnError(str(exc), code=_error_code(exc)) from exc
    thread_id = str(((started or {}).get("thread") or {}).get("id") or "")
    if not thread_id:
        raise CodexTurnError("codex did not start a thread")

    messages: list[str] = []
    generated: list[Path] = []
    usage: dict[str, int] = {}

    def on_notification(method: str, params: Mapping[str, Any]) -> None:
        if params.get("threadId") not in (None, thread_id):
            return
        if method == "item/completed":
            item = params.get("item") or {}
            kind = item.get("type")
            if kind == "agentMessage" and item.get("text"):
                messages.append(str(item["text"]))
            elif kind == "imageGeneration" and item.get("savedPath"):
                generated.append(Path(str(item["savedPath"])))
        elif method == "thread/tokenUsage/updated":
            last = ((params.get("tokenUsage") or {}).get("last")) or {}
            for key in ("inputTokens", "outputTokens", "cachedInputTokens"):
                if isinstance(last.get(key), int):
                    usage[key] = usage.get(key, 0) + last[key]

    remove = server.add_listener(on_notification)
    completion = server.expect_notification(
        "turn/completed", lambda params: params.get("threadId") in (None, thread_id)
    )
    inputs: list[dict[str, Any]] = [{"type": "text", "text": prompt, "text_elements": []}]
    inputs += [{"type": "localImage", "path": str(path)} for path in input_images]
    turn_params: dict[str, Any] = {"threadId": thread_id, "input": inputs}
    if output_schema is not None:
        turn_params["outputSchema"] = dict(output_schema)
    try:
        try:
            await server.request("turn/start", turn_params)
        except CodexRpcError as exc:
            completion.cancel()
            raise CodexTurnError(str(exc), code=_error_code(exc)) from exc
        done = await completion.wait(timeout=DEFAULT_TURN_TIMEOUT_SECONDS)
    except CodexRpcError as exc:
        raise CodexTurnError(str(exc), code=_error_code(exc)) from exc
    finally:
        remove()

    turn = done.get("turn") or {}
    if turn.get("status") != "completed":
        error = turn.get("error") or {}
        message = str(error.get("message") or f"codex turn {turn.get('status') or 'failed'}")
        raise CodexTurnError(message, code=_error_info_code(error))

    images = await asyncio.to_thread(_collect_images, generated, image_output_dir)
    text = messages[-1] if messages else ""
    if not text and not images:
        raise CodexTurnError("codex returned no output", code="empty_output")
    return CodexTurnResult(
        text=text,
        images=images,
        input_tokens=usage.get("inputTokens"),
        output_tokens=usage.get("outputTokens"),
        cached_input_tokens=usage.get("cachedInputTokens"),
    )


def _collect_images(paths: list[Path], output_dir: Path | None) -> list[Path]:
    if not paths:
        return []
    if output_dir is None:
        raise CodexTurnError("codex generated images but no output directory was given")
    output_dir.mkdir(parents=True, exist_ok=True)
    kept: list[Path] = []
    for index, source in enumerate(paths):
        if not source.is_file():
            continue
        target = output_dir / f"codex-image-{index}{source.suffix or '.png'}"
        shutil.copyfile(source, target)
        kept.append(target)
    return kept


def _error_info_code(error: Mapping[str, Any]) -> str | None:
    """把 Codex 的错误归到我们关心的几类：额度用完、要重新登录。"""
    info = error.get("codexErrorInfo")
    text = json.dumps(info).lower() if info is not None else str(error.get("message") or "").lower()
    if "usagelimit" in text.replace("_", "") or "rate" in text or "quota" in text:
        return "usage_limit"
    if "unauthorized" in text or "auth" in text or "login" in text:
        return "auth_required"
    return None


def _error_code(exc: CodexRpcError) -> str | None:
    with contextlib.suppress(Exception):
        return _error_info_code({"message": str(exc), "codexErrorInfo": exc.data})
    return None
