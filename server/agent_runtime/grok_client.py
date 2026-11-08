"""Grok 引擎的会话 client：驱动官方 ``grok agent stdio``（ACP），对 :class:`SessionActor` 说 Claude SDK 的帧协定。

与 :mod:`server.agent_runtime.codex_client` 同一种接缝（docs/adr/0124、0125）：

- 会话：``session/new``（恢复时 ``session/resume``，不支援时退回 ``session/load`` 并丢掉回放）；``sessionId`` 即事件日志的会话 id。
- 工具：ACP 只能经 MCP 接客户端的工具，所以本进程在 :mod:`server.agent_runtime.session_tool_endpoint` 登记这个会话的工具与
  令牌，``session/new`` 以 HTTP MCP 把端点交给 Grok。工具在本进程执行，执行前后由端点回呼写出 tool_use / tool_result 帧，
  不依赖 Grok 的工具更新格式。
- Grok 自带的工具：以 ``--disallowed-tools`` 移除、``--no-subagents``／``--disable-web-search`` 关闭，连线 HOME 的
  ``config.toml`` 另加权限 deny 规则；Grok 来要权限时只批准 ArcReel 工具，其余一律拒绝。
- 一轮：``session/prompt`` 进行中，``agent_message_chunk`` 的文字累积成一则 assistant 讯息；响应带 ``stopReason`` 即一轮结束。
  轮次进行中送来的讯息由 client 自己排队（ACP 同一会话一次一个 prompt）。中断送 ``session/cancel``。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from server.agent_runtime.engine_client import EngineClient
from server.agent_runtime.session_tool_endpoint import (
    SERVER_NAME,
    SessionToolRegistry,
    SessionTools,
    ToolCaller,
    session_tool_registry,
)

logger = logging.getLogger(__name__)

#: ArcReel 工具在前端与事件日志里的名字前缀（与 Claude、Codex 引擎相同）
ARCREEL_TOOL_PREFIX = "mcp__arcreel__"
_STDOUT_LIMIT = 16 * 1024 * 1024

#: Grok 内建、会碰档案系统、开子程序或上网的工具 ID（xAI 内建文件「Tool Filtering」一节列出的名字）；Agent 只用 ArcReel 工具
DISALLOWED_GROK_TOOLS: tuple[str, ...] = (
    "run_terminal_cmd",
    "task",
    "get_task_output",
    "wait_tasks",
    "kill_task",
    "read_file",
    "grep",
    "list_dir",
    "write",
    "search_replace",
    "web_search",
    "web_fetch",
    "lsp",
    "monitor",
    "workflow",
)

#: 连线 HOME 的 ``.grok/config.toml``：内建工具的权限一律拒绝（第二道防线；deny 优先于 allow）
GROK_PERMISSION_CONFIG = """# ArcReel 写入：内嵌 Agent 只用 ArcReel 工具，Grok 内建的档案、命令与网路工具一律拒绝。
[permission]
deny = ["Bash", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "LS", "WebFetch", "WebSearch", "Task", "Agent", "NotebookEdit"]
"""


@dataclass(frozen=True)
class GrokSessionConfig:
    """一个 Grok 会话的启动设定。"""

    grok_home: Path
    project_cwd: Path
    model: str | None
    #: 附加在 Grok 系统提示后的规则（语言规则、项目上下文、使用者记忆）
    rules: str | None
    tool_specs: list[dict[str, Any]]
    tool_callers: Mapping[str, ToolCaller]
    arcreel_tool_names: frozenset[str]
    #: 本机工具端点的完整网址，例如 ``http://127.0.0.1:1241/internal/agent-tools``
    tool_endpoint_url: str
    resume_session_id: str | None = None
    #: xAI API Key 连线：经 ``XAI_API_KEY`` 认证；订阅连线留空，用 HOME 里登录时存下的凭证
    api_key: str | None = None
    cli_path: str | None = None
    registry: SessionToolRegistry = field(default=session_tool_registry)


@dataclass
class _QueuedPrompt:
    message_uuid: str | None
    blocks: list[dict[str, Any]]


class GrokAcpError(Exception):
    """ACP 连线层面的失败：JSON-RPC 错误、进程提前结束或写入失败。"""


def write_permission_config(grok_home: Path) -> None:
    """把内建工具的 deny 规则写进连线 HOME 的 ``.grok/config.toml``；同步函数，呼叫端放进线程。"""
    config_dir = grok_home / ".grok"
    config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = config_dir / "config.toml"
    if path.exists() and path.read_text(encoding="utf-8") == GROK_PERMISSION_CONFIG:
        return
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text(GROK_PERMISSION_CONFIG, encoding="utf-8")
    os.replace(tmp, path)


class GrokAgentClient(EngineClient):
    """一个 Grok 会话。只在所属 SessionActor 的 task 里使用。"""

    def __init__(self, config: GrokSessionConfig, *, on_stderr: Callable[[str], None] | None = None) -> None:
        self._config = config
        self._on_stderr = on_stderr
        self._process: asyncio.subprocess.Process | None = None
        self._frames: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._pending_rpc: dict[int, asyncio.Future[Any]] = {}
        self._next_id = 0
        self._session_id: str | None = None
        self._model: str = config.model or "grok"
        self._token: str | None = None
        self._active: _QueuedPrompt | None = None
        self._queue: deque[_QueuedPrompt] = deque()
        self._text: list[str] = []
        self._turn_messages: list[str] = []
        self._turn_started_at = 0.0
        #: session/load 回放历史期间为 True：回放的更新不写成帧
        self._replaying = False
        self._closed = False
        self._background: set[asyncio.Task[Any]] = set()
        self._reader: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None

    # ---- async context manager ----

    async def __aenter__(self) -> GrokAgentClient:
        cli = self._config.cli_path or shutil.which("grok")
        if not cli:
            raise GrokAcpError("grok CLI not found")
        await asyncio.to_thread(write_permission_config, self._config.grok_home)
        args = [cli, "--no-auto-update", "--disallowed-tools", ",".join(DISALLOWED_GROK_TOOLS)]
        args += ["--no-subagents", "--disable-web-search"]
        if self._config.model:
            args += ["-m", self._config.model]
        if self._config.rules:
            args += ["--rules", self._config.rules]
        args += ["agent", "stdio"]
        env = {
            "HOME": str(self._config.grok_home),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "DISABLE_TELEMETRY": "1",
            "DISABLE_ERROR_REPORTING": "1",
        }
        if self._config.api_key:
            env["XAI_API_KEY"] = self._config.api_key
        try:
            self._process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(self._config.project_cwd),
                start_new_session=True,
                limit=_STDOUT_LIMIT,
            )
        except OSError as exc:
            raise GrokAcpError(f"failed to start grok: {exc}") from exc
        self._reader = asyncio.create_task(self._read_loop(), name="grok-agent-reader")
        self._stderr_task = asyncio.create_task(self._drain_stderr(), name="grok-agent-stderr")
        self._token = self._config.registry.register(
            SessionTools(
                specs=self._config.tool_specs,
                callers=self._config.tool_callers,
                on_start=self._on_tool_start,
                observer=self._on_tool_done,
            )
        )
        try:
            await self._request("initialize", {"protocolVersion": 1, "clientCapabilities": {}})
            await self._open_session()
        except BaseException:
            await self._shutdown()
            raise
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._shutdown()

    # ---- SessionActor 用到的方法 ----

    async def query(self, prompt: AsyncIterator[dict[str, Any]], session_id: str | None = None) -> None:
        del session_id
        async for message in prompt:
            queued = _to_prompt(message)
            if self._active is not None or self._queue:
                self._queue.append(queued)
                self._lifecycle(queued, "queued")
            else:
                self._start_prompt(queued)

    async def interrupt(self) -> None:
        if self._session_id is None or self._active is None:
            return
        with contextlib.suppress(GrokAcpError):
            await self._notify("session/cancel", {"sessionId": self._session_id})

    def raw_frames(self) -> AsyncIterator[dict[str, Any]]:
        return self._frame_stream()

    async def cancel_message(self, message_uuid: str) -> bool:
        for queued in list(self._queue):
            if queued.message_uuid == message_uuid:
                self._queue.remove(queued)
                self._lifecycle(queued, "cancelled")
                return True
        return False

    @property
    def session_id(self) -> str | None:
        return self._session_id

    # ---- 会话与轮次 ----

    def _mcp_servers(self) -> list[dict[str, Any]]:
        assert self._token is not None
        return [
            {
                "type": "http",
                "name": SERVER_NAME,
                "url": self._config.tool_endpoint_url,
                "headers": [{"name": "Authorization", "value": f"Bearer {self._token}"}],
            }
        ]

    async def _open_session(self) -> None:
        cwd = str(self._config.project_cwd)
        resume_id = self._config.resume_session_id
        if resume_id:
            try:
                await self._request(
                    "session/resume", {"sessionId": resume_id, "cwd": cwd, "mcpServers": self._mcp_servers()}
                )
            except GrokAcpError:
                self._replaying = True
                try:
                    await self._request(
                        "session/load", {"sessionId": resume_id, "cwd": cwd, "mcpServers": self._mcp_servers()}
                    )
                finally:
                    self._replaying = False
            self._session_id = resume_id
        else:
            response = await self._request("session/new", {"cwd": cwd, "mcpServers": self._mcp_servers()})
            self._session_id = str((response or {}).get("sessionId") or "")
            if not self._session_id:
                raise GrokAcpError("grok did not open a session")
        self._emit({"type": "system", "subtype": "init", "session_id": self._session_id, "model": self._model})

    def _start_prompt(self, queued: _QueuedPrompt) -> None:
        self._active = queued
        self._text = []
        self._turn_messages = []
        self._turn_started_at = time.monotonic()
        self._lifecycle(queued, "started")
        self._emit(
            {"type": "system", "subtype": "session_state_changed", "state": "running", "session_id": self._session_id}
        )
        self._spawn(self._run_prompt(queued), "grok-prompt")

    async def _run_prompt(self, queued: _QueuedPrompt) -> None:
        stop_reason: str | None = None
        error: str | None = None
        try:
            response = await self._request("session/prompt", {"sessionId": self._session_id, "prompt": queued.blocks})
            stop_reason = str((response or {}).get("stopReason") or "end_turn")
        except GrokAcpError as exc:
            error = str(exc)
        self._flush_text()
        self._finish(stop_reason, error)
        self._active = None
        if self._queue:
            self._start_prompt(self._queue.popleft())
        else:
            self._emit(
                {"type": "system", "subtype": "session_state_changed", "state": "idle", "session_id": self._session_id}
            )

    def _finish(self, stop_reason: str | None, error: str | None) -> None:
        if error is not None:
            subtype, is_error = "error_during_execution", True
        elif stop_reason == "cancelled":
            subtype, is_error = "interrupted", False
        elif stop_reason == "refusal":
            subtype, is_error = "error_during_execution", True
        else:
            subtype, is_error = "success", False
        result: dict[str, Any] = {
            "type": "result",
            "subtype": subtype,
            "duration_ms": int((time.monotonic() - self._turn_started_at) * 1000),
            "duration_api_ms": 0,
            "is_error": is_error,
            "num_turns": 1,
            "session_id": self._session_id,
            "result": self._turn_messages[-1] if self._turn_messages else None,
            "uuid": str(uuid.uuid4()),
        }
        if is_error:
            message = error or f"grok stopped: {stop_reason}"
            result["errors"] = [message]
            kind = grok_error_kind(message)
            if kind is not None:
                result["grok_error_kind"] = kind
        self._emit(result)
        if self._active is not None:
            self._lifecycle(self._active, "completed")

    def _lifecycle(self, queued: _QueuedPrompt, state: str) -> None:
        if queued.message_uuid:
            self._emit({"type": "command_lifecycle", "command_uuid": queued.message_uuid, "state": state})

    # ---- 工具（本机端点回呼） ----

    def _on_tool_start(self, call_id: str, tool: str, arguments: Any) -> None:
        self._flush_text()
        self._emit_assistant(
            [
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": self._display_tool_name(tool),
                    "input": arguments if isinstance(arguments, dict) else {},
                }
            ]
        )

    def _on_tool_done(self, call_id: str, result: Mapping[str, Any]) -> None:
        texts = [
            str(entry.get("text"))
            for entry in result.get("contentItems") or []
            if isinstance(entry, Mapping) and entry.get("type") == "inputText"
        ]
        self._emit(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": call_id,
                            "content": "\n".join(texts),
                            "is_error": result.get("success") is False,
                        }
                    ],
                },
                "parent_tool_use_id": None,
                "session_id": self._session_id,
                "uuid": str(uuid.uuid4()),
            }
        )

    def _display_tool_name(self, tool: str) -> str:
        return f"{ARCREEL_TOOL_PREFIX}{tool}" if tool in self._config.arcreel_tool_names else tool

    # ---- ACP 讯息 ----

    def _on_notification(self, method: str, params: Mapping[str, Any]) -> None:
        if method != "session/update" or self._replaying:
            return
        if params.get("sessionId") not in (None, self._session_id):
            return
        update = params.get("update")
        if not isinstance(update, Mapping):
            return
        kind = update.get("sessionUpdate")
        content = update.get("content")
        if kind == "agent_message_chunk" and isinstance(content, Mapping) and content.get("type") == "text":
            text = content.get("text")
            if isinstance(text, str):
                self._text.append(text)

    async def _answer_request(self, message_id: Any, method: str, params: Mapping[str, Any]) -> None:
        if method == "session/request_permission":
            reply: dict[str, Any] = {"jsonrpc": "2.0", "id": message_id, "result": _permission_outcome(params)}
        else:
            # fs/*、terminal/* 等：本 client 不提供档案与终端能力
            reply = {"jsonrpc": "2.0", "id": message_id, "error": {"code": -32601, "message": f"unsupported: {method}"}}
        with contextlib.suppress(GrokAcpError):
            await self._write(reply)

    async def _request(self, method: str, params: Mapping[str, Any]) -> Any:
        if self._closed:
            raise GrokAcpError("grok connection is closed")
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending_rpc[request_id] = future
        try:
            await self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)})
            return await future
        finally:
            self._pending_rpc.pop(request_id, None)

    async def _notify(self, method: str, params: Mapping[str, Any]) -> None:
        await self._write({"jsonrpc": "2.0", "method": method, "params": dict(params)})

    async def _write(self, message: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.stdin.is_closing():
            raise GrokAcpError("grok stdin is closed")
        process.stdin.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
        try:
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise GrokAcpError("grok exited") from exc

    async def _read_loop(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        stdout = self._process.stdout
        try:
            while True:
                line = await stdout.readline()
                if not line:
                    break
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict):
                    self._dispatch(message)
        finally:
            for future in self._pending_rpc.values():
                if not future.done():
                    future.set_exception(GrokAcpError("grok exited"))

    def _dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        message_id = message.get("id")
        if method is None and message_id is not None:
            future = self._pending_rpc.get(message_id)
            if future is None or future.done():
                return
            error = message.get("error")
            if error is not None:
                future.set_exception(GrokAcpError(str((error or {}).get("message") or "error")))
            else:
                future.set_result(message.get("result"))
            return
        params = message.get("params") or {}
        if not isinstance(method, str):
            return
        if message_id is not None:
            self._spawn(self._answer_request(message_id, method, params), f"grok-request-{method}")
        else:
            self._on_notification(method, params)

    async def _drain_stderr(self) -> None:
        assert self._process is not None
        assert self._process.stderr is not None
        while True:
            line = await self._process.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", "replace").rstrip()
            logger.debug("grok stderr: %s", text)
            if self._on_stderr is not None:
                with contextlib.suppress(Exception):
                    self._on_stderr(text)

    # ---- 帧 ----

    def _flush_text(self) -> None:
        if not self._text:
            return
        text = "".join(self._text)
        self._text = []
        if text.strip():
            self._turn_messages.append(text)
            self._emit_assistant([{"type": "text", "text": text}])

    def _emit_assistant(self, content: list[dict[str, Any]]) -> None:
        self._emit(
            {
                "type": "assistant",
                "message": {
                    "id": f"grok-{uuid.uuid4().hex}",
                    "type": "message",
                    "role": "assistant",
                    "model": self._model,
                    "content": content,
                    "stop_reason": None,
                },
                "parent_tool_use_id": None,
                "session_id": self._session_id,
                "uuid": str(uuid.uuid4()),
            }
        )

    async def _frame_stream(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            frame = await self._frames.get()
            if frame is None:
                return
            yield frame

    def _emit(self, frame: dict[str, Any]) -> None:
        if not self._closed:
            self._frames.put_nowait(frame)

    def _spawn(self, coro: Any, name: str) -> None:
        task = asyncio.get_running_loop().create_task(coro, name=name)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._token is not None:
            self._config.registry.unregister(self._token)
        for task in list(self._background):
            task.cancel()
        process = self._process
        if process is not None and process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(process.wait(), timeout=5)
        for task in (self._reader, self._stderr_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._frames.put_nowait(None)


def _permission_outcome(params: Mapping[str, Any]) -> dict[str, Any]:
    """只批准 ArcReel 工具（经本机工具端点的 MCP 呼叫）；Grok 内建工具一律拒绝。"""
    options = [o for o in params.get("options") or [] if isinstance(o, Mapping)]
    tool_call = params.get("toolCall") or {}
    described = json.dumps(tool_call, ensure_ascii=False).lower()
    ours = SERVER_NAME in described or ARCREEL_TOOL_PREFIX in described
    wanted = ("allow_once", "allow_always") if ours else ("reject_once", "reject_always")
    for kind in wanted:
        for option in options:
            if option.get("kind") == kind and option.get("optionId"):
                return {"outcome": {"outcome": "selected", "optionId": option["optionId"]}}
    return {"outcome": {"outcome": "cancelled"}}


def grok_error_kind(message: str) -> str | None:
    """把错误讯息归到额度用完或要重新登录。"""
    text = message.lower()
    if any(token in text for token in ("limit", "quota", "rate")):
        return "quota"
    if any(token in text for token in ("auth", "sign in", "login", "unauthorized")):
        return "auth"
    return None


def _to_prompt(message: Mapping[str, Any]) -> _QueuedPrompt:
    """SDK 串流输入的使用者讯息 → ACP ``session/prompt`` 的内容块。"""
    body = message.get("message") or {}
    content = body.get("content") if isinstance(body, Mapping) else None
    blocks: list[dict[str, Any]] = []
    if isinstance(content, str):
        blocks.append({"type": "text", "text": content})
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, Mapping):
                continue
            if block.get("type") == "text" and block.get("text"):
                blocks.append({"type": "text", "text": str(block["text"])})
            elif block.get("type") == "image":
                source = block.get("source") or {}
                if source.get("type") == "base64" and source.get("data"):
                    blocks.append(
                        {
                            "type": "image",
                            "mimeType": str(source.get("media_type") or "image/png"),
                            "data": str(source["data"]),
                        }
                    )
    uid = message.get("uuid")
    return _QueuedPrompt(message_uuid=str(uid) if uid else None, blocks=blocks)


__all__ = [
    "DISALLOWED_GROK_TOOLS",
    "GROK_PERMISSION_CONFIG",
    "GrokAcpError",
    "GrokAgentClient",
    "GrokSessionConfig",
    "grok_error_kind",
    "write_permission_config",
]
