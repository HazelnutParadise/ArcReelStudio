"""Agent 的 Codex 引擎：驱动 ``codex app-server``，对 SessionActor 提供与 ``ClaudeSDKClient`` 相同的用法。

接缝在 SessionActor 的 ``client_factory``：这个 client 是 async context manager，提供 ``query`` / ``interrupt``，并以
:meth:`raw_frames` / :meth:`cancel_message` 取代 Claude SDK 的私有入口（见 :mod:`server.agent_runtime.sdk_frames`）。
它把 Codex 的事件改写成 Claude CLI 的 wire 帧（``assistant`` / ``user`` / ``system`` / ``result`` /
``command_lifecycle``），之后的 SDK 解析、事件日志、用量与前端都不必知道换了引擎。

- **工具**：Codex 自带的 shell、命令执行、子代理、看图与生图全部关闭；ArcReel 工具集与受访问规则约束的文件工具以
  dynamic tools 提供（``item/tool/call`` 在本进程执行）。其他服务器请求（批准、提问等）一律拒绝。
- **专案指引与技能**：Codex 原生读 cwd 的指引文件，``project_doc_fallback_filenames`` 让它读物化到专案的 ``CLAUDE.md``；
  技能以 ``skills/extraRoots/set`` 指到专案的 ``.claude/skills``。会话固定的附加提示（语言规则、专案上下文、使用者记忆）
  走 ``developerInstructions``。
- **排队**：Codex 在一轮进行中再收到输入会并入当前轮，ArcReel 的语意是排队，所以这里自持佇列：一轮进行中到达的讯息先
  回 ``queued``，这一轮结束后依序开新的一轮；``cancel_message`` 从佇列撤回。
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import tempfile
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib.agent.codex_app_server import CodexAppServer, CodexRpcError

logger = logging.getLogger(__name__)

#: 关掉 Codex 自带、会碰档案系统或开子程序的工具；档案读写改由受访问规则约束的 dynamic tools 提供
DISABLED_CODEX_FEATURES = ("shell_tool", "unified_exec", "multi_agent", "view_image", "image_generation")
#: ArcReel 工具在前端与事件日志里的名字前缀（与 Claude 引擎的 in-process MCP server 相同）
ARCREEL_TOOL_PREFIX = "mcp__arcreel__"

ToolCaller = Callable[[str, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class CodexSessionConfig:
    """一个 Codex 会话的启动设定。"""

    codex_home: Path
    project_cwd: Path
    model: str | None
    developer_instructions: str | None
    tool_specs: list[dict[str, Any]]
    #: dynamic tool 名 → 执行函数（arguments → Codex 工具结果）
    tool_callers: Mapping[str, ToolCaller]
    #: 名字在事件日志里要加 ``mcp__arcreel__`` 前缀的工具（ArcReel 工具集；档案工具保持 Read/Write 等原名）
    arcreel_tool_names: frozenset[str]
    skill_roots: tuple[Path, ...] = ()
    #: 恢复既有会话时的 Codex thread id
    resume_thread_id: str | None = None
    #: OpenAI API Key 连线：首次启动时以 apiKey 登入这个 CODEX_HOME
    api_key: str | None = None
    cli_path: str | None = None
    extra_config: tuple[str, ...] = ()


@dataclass
class _QueuedQuery:
    message_uuid: str | None
    inputs: list[dict[str, Any]]
    temp_files: list[Path] = field(default_factory=list)


class CodexAgentClient:
    """一个 Codex 会话。只在所属 SessionActor 的 task 里使用。"""

    def __init__(self, config: CodexSessionConfig, *, on_stderr: Callable[[str], None] | None = None) -> None:
        self._config = config
        self._on_stderr = on_stderr
        self._server: CodexAppServer | None = None
        self._frames: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._thread_id: str | None = None
        self._model: str = config.model or "codex"
        self._active_turn_id: str | None = None
        self._active_query: _QueuedQuery | None = None
        self._pending: deque[_QueuedQuery] = deque()
        self._turn_started_at = 0.0
        self._turn_messages: list[str] = []
        self._usage_total: dict[str, int] = {}
        self._remove_listener: Callable[[], None] | None = None
        self._closed = False
        # 轮次结束后在背景做的事（开下一轮、删临时档）；留引用免得任务被回收
        self._background: set[asyncio.Task[Any]] = set()

    # ---- async context manager ----

    async def __aenter__(self) -> CodexAgentClient:
        overrides = [f"features.{name}=false" for name in DISABLED_CODEX_FEATURES]
        overrides.append('project_doc_fallback_filenames=["CLAUDE.md"]')
        overrides.extend(self._config.extra_config)
        self._server = await CodexAppServer.start(
            str(self._config.codex_home),
            cli_path=self._config.cli_path,
            config_overrides=tuple(overrides),
            on_server_request=self._on_server_request,
            on_stderr=self._on_stderr,
        )
        try:
            self._remove_listener = self._server.add_listener(self._on_notification)
            if self._config.api_key:
                await self._ensure_api_key_login(self._config.api_key)
            if self._config.skill_roots:
                with contextlib.suppress(CodexRpcError):
                    await self._server.request(
                        "skills/extraRoots/set", {"extraRoots": [str(root) for root in self._config.skill_roots]}
                    )
            await self._open_thread()
        except BaseException:
            await self._shutdown()
            raise
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._shutdown()

    # ---- SessionActor 用到的方法 ----

    async def query(self, prompt: AsyncIterator[dict[str, Any]], session_id: str | None = None) -> None:
        """送出一则使用者讯息；有一轮进行中时先排队。"""
        del session_id
        async for message in prompt:
            queued = await asyncio.to_thread(_to_codex_input, message)
            if self._active_turn_id is not None or self._pending:
                self._pending.append(queued)
                self._lifecycle(queued, "queued")
            else:
                await self._start_turn(queued)

    async def interrupt(self) -> None:
        if self._server is None or self._thread_id is None or self._active_turn_id is None:
            return
        with contextlib.suppress(CodexRpcError):
            await self._server.request(
                "turn/interrupt", {"threadId": self._thread_id, "turnId": self._active_turn_id}, timeout=15
            )

    def raw_frames(self) -> AsyncIterator[dict[str, Any]]:
        return self._frame_stream()

    async def cancel_message(self, message_uuid: str) -> bool:
        for queued in list(self._pending):
            if queued.message_uuid == message_uuid:
                self._pending.remove(queued)
                self._lifecycle(queued, "cancelled")
                await asyncio.to_thread(_remove_files, queued.temp_files)
                return True
        return False

    @property
    def thread_id(self) -> str | None:
        return self._thread_id

    # ---- 内部 ----

    async def _frame_stream(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            frame = await self._frames.get()
            if frame is None:
                return
            yield frame

    def _emit(self, frame: dict[str, Any]) -> None:
        if not self._closed:
            self._frames.put_nowait(frame)

    async def _ensure_api_key_login(self, api_key: str) -> None:
        assert self._server is not None
        account = await self._server.request("account/read", {"refreshToken": False})
        if isinstance(account, dict) and account.get("account"):
            return
        await self._server.request("account/login/start", {"type": "apiKey", "apiKey": api_key})

    async def _open_thread(self) -> None:
        assert self._server is not None
        params: dict[str, Any] = {
            "cwd": str(self._config.project_cwd),
            "sandbox": "read-only",
            "approvalPolicy": "never",
            "dynamicTools": self._config.tool_specs,
        }
        if self._config.model:
            params["model"] = self._config.model
        if self._config.developer_instructions:
            params["developerInstructions"] = self._config.developer_instructions
        if self._config.resume_thread_id:
            response = await self._server.request(
                "thread/resume", {"threadId": self._config.resume_thread_id, **params}
            )
        else:
            response = await self._server.request("thread/start", params)
        thread = (response or {}).get("thread") or {}
        self._thread_id = str(thread.get("id") or self._config.resume_thread_id or "")
        if not self._thread_id:
            raise CodexRpcError("codex did not open a thread")
        model = (response or {}).get("model")
        if isinstance(model, str) and model:
            self._model = model
        self._emit({"type": "system", "subtype": "init", "session_id": self._thread_id, "model": self._model})

    async def _start_turn(self, queued: _QueuedQuery) -> None:
        assert self._server is not None
        assert self._thread_id is not None
        self._active_query = queued
        self._turn_messages = []
        self._turn_started_at = time.monotonic()
        params: dict[str, Any] = {"threadId": self._thread_id, "input": queued.inputs}
        try:
            response = await self._server.request("turn/start", params)
        except CodexRpcError:
            self._active_query = None
            await asyncio.to_thread(_remove_files, queued.temp_files)
            raise
        turn = (response or {}).get("turn") or {}
        self._active_turn_id = str(turn.get("id") or "") or None
        self._lifecycle(queued, "started")
        self._emit(
            {"type": "system", "subtype": "session_state_changed", "state": "running", "session_id": self._thread_id}
        )

    def _lifecycle(self, queued: _QueuedQuery, state: str) -> None:
        if queued.message_uuid:
            self._emit({"type": "command_lifecycle", "command_uuid": queued.message_uuid, "state": state})

    async def _on_server_request(self, method: str, params: Mapping[str, Any]) -> Any:
        if method == "item/tool/call":
            tool = str(params.get("tool") or "")
            caller = self._config.tool_callers.get(tool)
            if caller is None:
                return {"contentItems": [{"type": "inputText", "text": f"Tool '{tool}' not found"}], "success": False}
            return await caller(tool, params.get("arguments"))
        # 其他请求（批准执行、改档、提问等）：本引擎不开放 Codex 自带工具，一律拒绝
        raise CodexRpcError(f"unsupported request: {method}")

    def _on_notification(self, method: str, params: Mapping[str, Any]) -> None:
        if params.get("threadId") not in (None, self._thread_id):
            return
        if method == "item/started":
            self._on_item_started(params.get("item") or {})
        elif method == "item/completed":
            self._on_item_completed(params.get("item") or {})
        elif method == "thread/tokenUsage/updated":
            total = ((params.get("tokenUsage") or {}).get("total")) or {}
            self._usage_total = {k: v for k, v in total.items() if isinstance(v, int)}
        elif method == "turn/completed":
            self._on_turn_completed(params.get("turn") or {})

    def _on_item_started(self, item: Mapping[str, Any]) -> None:
        if item.get("type") != "dynamicToolCall":
            return
        tool = str(item.get("tool") or "")
        self._emit_assistant(
            [
                {
                    "type": "tool_use",
                    "id": str(item.get("id") or uuid.uuid4().hex),
                    "name": self._display_tool_name(tool),
                    "input": item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                }
            ]
        )

    def _on_item_completed(self, item: Mapping[str, Any]) -> None:
        kind = item.get("type")
        if kind == "agentMessage" and item.get("text"):
            text = str(item["text"])
            self._turn_messages.append(text)
            self._emit_assistant([{"type": "text", "text": text}], message_id=str(item.get("id") or ""))
        elif kind == "reasoning":
            summary = "\n".join(str(part) for part in item.get("summary") or [] if part)
            if summary:
                self._emit_assistant([{"type": "thinking", "thinking": summary, "signature": ""}])
        elif kind == "dynamicToolCall":
            texts = [
                str(entry.get("text"))
                for entry in item.get("contentItems") or []
                if isinstance(entry, dict) and entry.get("type") == "inputText"
            ]
            self._emit(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": str(item.get("id") or ""),
                                "content": "\n".join(texts),
                                "is_error": item.get("success") is False,
                            }
                        ],
                    },
                    "parent_tool_use_id": None,
                    "session_id": self._thread_id,
                    "uuid": str(uuid.uuid4()),
                }
            )

    def _on_turn_completed(self, turn: Mapping[str, Any]) -> None:
        status = turn.get("status")
        error = turn.get("error") or {}
        finished = self._active_query
        self._active_turn_id = None
        self._active_query = None
        if status == "completed":
            subtype, is_error = "success", False
        elif status == "interrupted":
            subtype, is_error = "interrupted", False
        else:
            subtype, is_error = "error_during_execution", True
        usage = self._usage_total
        cached = usage.get("cachedInputTokens", 0)
        result: dict[str, Any] = {
            "type": "result",
            "subtype": subtype,
            "duration_ms": int((time.monotonic() - self._turn_started_at) * 1000),
            "duration_api_ms": 0,
            "is_error": is_error,
            "num_turns": 1,
            "session_id": self._thread_id,
            "result": self._turn_messages[-1] if self._turn_messages else None,
            "modelUsage": {
                self._model: {
                    "inputTokens": max(usage.get("inputTokens", 0) - cached, 0),
                    "cacheReadInputTokens": cached,
                    "cacheCreationInputTokens": usage.get("cacheWriteInputTokens", 0),
                    "outputTokens": usage.get("outputTokens", 0),
                }
            },
            "uuid": str(uuid.uuid4()),
        }
        if is_error:
            result["errors"] = [str(error.get("message") or "codex turn failed")]
            info = codex_error_kind(error)
            if info is not None:
                result["codex_error_kind"] = info
        self._emit(result)
        if finished is not None:
            self._lifecycle(finished, "completed")
        self._spawn(self._after_turn(finished), "codex-after-turn")

    async def _after_turn(self, finished: _QueuedQuery | None) -> None:
        """轮次收尾：先删本轮的临时图片，再开下一轮或宣告闲置，保证闲置时不留临时档。"""
        if finished is not None and finished.temp_files:
            await asyncio.to_thread(_remove_files, finished.temp_files)
        if self._pending:
            await self._start_turn(self._pending.popleft())
        else:
            self._emit(
                {"type": "system", "subtype": "session_state_changed", "state": "idle", "session_id": self._thread_id}
            )

    def _spawn(self, coro: Awaitable[Any], name: str) -> None:
        task = asyncio.get_running_loop().create_task(_await(coro), name=name)
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    def _emit_assistant(self, content: list[dict[str, Any]], *, message_id: str = "") -> None:
        self._emit(
            {
                "type": "assistant",
                "message": {
                    "id": message_id or f"codex-{uuid.uuid4().hex}",
                    "type": "message",
                    "role": "assistant",
                    "model": self._model,
                    "content": content,
                    "stop_reason": None,
                },
                "parent_tool_use_id": None,
                "session_id": self._thread_id,
                "uuid": str(uuid.uuid4()),
            }
        )

    def _display_tool_name(self, tool: str) -> str:
        return f"{ARCREEL_TOOL_PREFIX}{tool}" if tool in self._config.arcreel_tool_names else tool

    async def _shutdown(self) -> None:
        if self._closed:
            return
        if self._remove_listener is not None:
            self._remove_listener()
        for task in list(self._background):
            task.cancel()
        if self._server is not None:
            await self._server.close()
        self._closed = True
        self._frames.put_nowait(None)
        leftovers = [*([self._active_query] if self._active_query else []), *self._pending]
        await asyncio.to_thread(_remove_files, [path for q in leftovers for path in q.temp_files])


async def _await(coro: Awaitable[Any]) -> Any:
    return await coro


def codex_error_kind(error: Mapping[str, Any]) -> str | None:
    """Codex 的轮次错误归类：``usage_limit``（额度或速率）、``auth``（要重新登入）。"""
    info = error.get("codexErrorInfo")
    text = (str(info) if info is not None else str(error.get("message") or "")).lower()
    if "usagelimit" in text.replace("_", "") or "ratelimit" in text.replace("_", "") or "quota" in text:
        return "usage_limit"
    if "unauthorized" in text or "auth" in text or "login" in text:
        return "auth"
    return None


def _to_codex_input(message: Mapping[str, Any]) -> _QueuedQuery:
    """SDK 串流输入的使用者讯息 → Codex ``turn/start`` 的输入：文字原样、图片存成临时档后以 localImage 送。"""
    body = message.get("message") or {}
    content = body.get("content") if isinstance(body, dict) else None
    inputs: list[dict[str, Any]] = []
    temp_files: list[Path] = []
    if isinstance(content, str):
        inputs.append({"type": "text", "text": content, "text_elements": []})
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                inputs.append({"type": "text", "text": str(block["text"]), "text_elements": []})
            elif block.get("type") == "image":
                source = block.get("source") or {}
                if source.get("type") == "base64" and source.get("data"):
                    suffix = "." + str(source.get("media_type") or "image/png").split("/")[-1]
                    fd, name = tempfile.mkstemp(prefix="codex-input-", suffix=suffix)
                    with open(fd, "wb") as handle:
                        handle.write(base64.b64decode(source["data"]))
                    temp_files.append(Path(name))
                    inputs.append({"type": "localImage", "path": name})
    uid = message.get("uuid")
    return _QueuedQuery(message_uuid=str(uid) if uid else None, inputs=inputs, temp_files=temp_files)


def _remove_files(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)  # hard-delete: temp -- 送给 Codex 的临时图片档
