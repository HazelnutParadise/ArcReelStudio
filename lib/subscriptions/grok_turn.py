"""用 Grok 订阅跑一次性的一轮文字：经 ``grok agent stdio``（ACP，JSON-RPC 2.0 over stdio）。

流程（xAI 文档 https://docs.x.ai/build/cli/headless-scripting.md 的 ACP 一节）：
1. 起 ``grok --no-auto-update [-m <model>] agent stdio``，环境里 ``HOME`` 是连线专属的 HOME（凭证在其中的 ``.grok``）。
2. 发 ``initialize``（``protocolVersion: 1``、``clientCapabilities: {}``），再发 ``session/new``（``cwd`` 是临时工作目录、
   ``mcpServers: []``），拿 ``sessionId``。
3. 发 ``session/prompt``（``sessionId``、``prompt: [{"type": "text", "text": ...}]``）；回复文字以 ``session/update`` 通知
   陆续到达（``params.update.sessionUpdate == "agent_message_chunk"`` 时取 ``params.update.content.text``，按到达顺序拼接），
   ``session/prompt`` 的响应带 ``stopReason`` 表示这一轮结束。
4. 服务器发来的请求（例如 ``session/request_permission``、``fs/*``）一律拒绝：回 JSON-RPC 错误 ``-32601``。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: 一轮最长等多久
DEFAULT_TURN_TIMEOUT_SECONDS = 10 * 60.0

#: stdout 一行可能很长（整段回复塞进一帧通知时），读缓冲开大一点
_STDOUT_LIMIT = 16 * 1024 * 1024


class GrokTurnError(Exception):
    """这一轮没有完成。``code``：``cli_unavailable``（起不了进程）、``auth_required``（未登录或凭证失效）、
    ``usage_limit``（额度用完）、``timeout``、``empty_output``（没有任何回复文字）、``None``（其他）。"""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class GrokTurnResult:
    text: str
    stop_reason: str | None = None


class _AcpError(Exception):
    """ACP 连接层面的失败：JSON-RPC 错误、进程提前结束或写入失败。"""


class _AcpConnection:
    """一个 ``grok agent stdio`` 进程的 JSON-RPC 2.0 客户端（每则讯息都带 ``jsonrpc: "2.0"``）。"""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._closed = asyncio.Event()
        #: ``agent_message_chunk`` 的文字，按到达顺序
        self.chunks: list[str] = []
        # 正在回答的服务器请求；留引用免得任务被回收（ruff asyncio-dangling-task）
        self._answering: set[asyncio.Task[None]] = set()
        self._reader = asyncio.create_task(self._read_loop(), name="grok-acp-reader")

    async def request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        if self._closed.is_set():
            raise _AcpError("grok ACP connection is closed")
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params or {})})
            return await future
        finally:
            self._pending.pop(request_id, None)

    async def close(self) -> None:
        if self._process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._process.kill()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._process.wait(), timeout=5)
        self._closed.set()
        self._reader.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._reader
        self._fail_pending(_AcpError("grok ACP connection is closed"))

    async def _write(self, message: Mapping[str, Any]) -> None:
        stdin = self._process.stdin
        if stdin is None or stdin.is_closing():
            raise _AcpError("grok ACP stdin is closed")
        stdin.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
        try:
            await stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise _AcpError("grok ACP connection exited") from exc

    async def _read_loop(self) -> None:
        stdout = self._process.stdout
        assert stdout is not None
        try:
            while True:
                line = await stdout.readline()
                if not line:
                    break
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug("grok ACP: non-JSON line ignored")
                    continue
                if isinstance(message, dict):
                    self._dispatch(message)
        finally:
            self._closed.set()
            self._fail_pending(_AcpError("grok ACP connection exited"))

    def _dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        message_id = message.get("id")
        if method is None and message_id is not None:
            future = self._pending.get(message_id)
            if future is None or future.done():
                return
            if message.get("error") is not None:
                error = message["error"] or {}
                future.set_exception(_AcpError(str(error.get("message") or "error")))
            else:
                future.set_result(message.get("result"))
            return
        params = message.get("params") or {}
        if message_id is not None and isinstance(method, str):
            # 服务器发来的请求：在独立任务里回答，不卡住读循环
            task = asyncio.create_task(self._answer(message_id, method), name=f"grok-server-request-{method}")
            self._answering.add(task)
            task.add_done_callback(self._answering.discard)
            return
        if isinstance(method, str):
            self._on_notification(method, params)

    def _on_notification(self, method: str, params: Mapping[str, Any]) -> None:
        if method != "session/update":
            return
        update = params.get("update")
        if not isinstance(update, Mapping) or update.get("sessionUpdate") != "agent_message_chunk":
            return
        content = update.get("content")
        if isinstance(content, Mapping) and content.get("type") == "text":
            text = content.get("text")
            if isinstance(text, str):
                self.chunks.append(text)

    async def _answer(self, message_id: Any, method: str) -> None:
        reply = {
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {"code": -32601, "message": f"unsupported: {method}"},
        }
        with contextlib.suppress(_AcpError):
            await self._write(reply)

    def _fail_pending(self, error: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)


def _error_code(message: str) -> str | None:
    """把错误讯息归到我们关心的几类：要重新登录、额度用完。"""
    text = message.lower()
    if any(token in text for token in ("sign", "auth", "login")):
        return "auth_required"
    if any(token in text for token in ("limit", "quota", "rate")):
        return "usage_limit"
    return None


def _grok_cli_path() -> str | None:
    return shutil.which("grok")


async def run_grok_turn(
    grok_home: Path,
    prompt: str,
    *,
    model: str | None = None,
    system_prompt: str | None = None,
    cli_path: str | None = None,
    timeout: float = DEFAULT_TURN_TIMEOUT_SECONDS,  # noqa: ASYNC109 -- 一轮的等待上限，由 asyncio.wait_for 实现；仓库无 trio/anyio cancel scope
) -> GrokTurnResult:
    """跑一轮并返回拼好的回复文字。

    - ``system_prompt`` 非空时放在 ``prompt`` 前面，中间空一行，作为同一段文字送出。
    - ``cli_path`` 为 None 时用 PATH 上的 ``grok``，找不到就抛 ``GrokTurnError(code="cli_unavailable")``。
    - 进程的环境只带 ``HOME``（= ``grok_home``）、``PATH``、``LANG``，不继承其他环境变量。
    - 收到 JSON-RPC 错误或进程提前结束：错误讯息含 "sign" / "auth" / "login" 时 ``code="auth_required"``，含
      "limit" / "quota" / "rate" 时 ``code="usage_limit"``，其他 ``code=None``。
    - 超过 ``timeout``：``code="timeout"``。回复文字为空：``code="empty_output"``。
    - 不论成败，结束前都结束子进程并删除临时工作目录。
    """
    cli = cli_path or _grok_cli_path()
    if not cli:
        raise GrokTurnError("grok CLI not found on PATH", code="cli_unavailable")

    work_dir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="grok-turn-"))
    try:
        args = [cli, "--no-auto-update"]
        if model:
            args += ["-m", model]
        args += ["agent", "stdio"]
        env = {
            "HOME": str(grok_home),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
                cwd=str(work_dir),
                start_new_session=True,
                limit=_STDOUT_LIMIT,
            )
        except OSError as exc:
            raise GrokTurnError(f"failed to start grok: {exc}", code="cli_unavailable") from exc

        connection = _AcpConnection(process)
        try:
            return await asyncio.wait_for(
                _run_turn(connection, work_dir, prompt, system_prompt),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise GrokTurnError("grok turn timed out", code="timeout") from exc
        finally:
            await connection.close()
    finally:
        await asyncio.to_thread(shutil.rmtree, work_dir, True)  # hard-delete: temp -- 这一轮专用的临时工作目录


async def _run_turn(
    connection: _AcpConnection,
    work_dir: Path,
    prompt: str,
    system_prompt: str | None,
) -> GrokTurnResult:
    try:
        await connection.request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        created = await connection.request("session/new", {"cwd": str(work_dir), "mcpServers": []})
        session_id = str((created or {}).get("sessionId") or "")
        if not session_id:
            raise GrokTurnError("grok did not start a session")
        text = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"
        result = await connection.request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
        )
    except _AcpError as exc:
        raise GrokTurnError(str(exc), code=_error_code(str(exc))) from exc

    reply = "".join(connection.chunks)
    if not reply:
        raise GrokTurnError("grok returned no output", code="empty_output")
    raw_stop_reason = (result or {}).get("stopReason")
    stop_reason = raw_stop_reason if isinstance(raw_stop_reason, str) else None
    return GrokTurnResult(text=reply, stop_reason=stop_reason)
