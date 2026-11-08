"""与 ``codex app-server`` 对话的最小 JSON-RPC 客户端。

app-server 走 stdio，一行一条 JSON-RPC 消息（不带 ``jsonrpc`` 字段）。客户端发请求、收响应与通知；服务器也会
反过来发请求（工具调用、权限确认等），交给 ``on_server_request`` 回答，没有处理器时回「方法不存在」。

每个实例用调用方给的 ``CODEX_HOME``：登录、令牌与会话都只落在那个目录里，不会读到容器里别的 Codex 状态。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

CLIENT_NAME = "arcreel"
CLIENT_VERSION = "1"
DEFAULT_REQUEST_TIMEOUT = 60.0
#: 让 Codex 把登录凭证写成 ``CODEX_HOME/auth.json``，不放系统钥匙圈，方便我们读出来存进数据库
_FILE_CREDENTIAL_STORE = 'cli_auth_credentials_store="file"'

ServerRequestHandler = Callable[[str, Mapping[str, Any]], Awaitable[Any]]


class CodexRpcError(Exception):
    """app-server 回了 JSON-RPC 错误、提前结束或超时。"""

    def __init__(self, message: str, *, code: int | None = None, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


def codex_cli_path() -> str | None:
    return shutil.which("codex")


class NotificationWaiter:
    """:meth:`CodexAppServer.expect_notification` 的结果；``wait`` 只能调用一次。"""

    def __init__(
        self,
        server: CodexAppServer,
        method: str,
        future: asyncio.Future[Mapping[str, Any]],
        remove: Callable[[], None],
    ) -> None:
        self._server = server
        self._method = method
        self._future = future
        self._remove = remove

    async def wait(self, *, timeout: float) -> Mapping[str, Any]:  # noqa: ASYNC109 -- 单次 JSON-RPC 等待上限，由 asyncio.wait/wait_for 实现；仓库无 trio/anyio cancel scope
        return await self._server._wait_registered(self._method, self._future, self._remove, timeout=timeout)

    def cancel(self) -> None:
        self._remove()
        self._future.cancel()


class CodexAppServer:
    """一个 ``codex app-server`` 进程。用 :meth:`start` 建立，用完 :meth:`close`。"""

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        *,
        on_server_request: ServerRequestHandler | None = None,
    ) -> None:
        self._process = process
        self._on_server_request = on_server_request
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._listeners: list[Callable[[str, Mapping[str, Any]], None]] = []
        self._closed = asyncio.Event()
        # 正在回答的服务器请求；留引用免得任务被回收
        self._answering: set[asyncio.Task[None]] = set()
        self._reader = asyncio.create_task(self._read_loop(), name="codex-app-server-reader")
        self._stderr_drain = asyncio.create_task(self._drain_stderr(), name="codex-app-server-stderr")

    @classmethod
    async def start(
        cls,
        codex_home: str,
        *,
        cli_path: str | None = None,
        extra_env: Mapping[str, str] | None = None,
        config_overrides: tuple[str, ...] = (),
        on_server_request: ServerRequestHandler | None = None,
    ) -> CodexAppServer:
        cli = cli_path or codex_cli_path()
        if not cli:
            raise CodexRpcError("codex CLI not found")
        env = {
            "CODEX_HOME": codex_home,
            "HOME": codex_home,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            **(extra_env or {}),
        }
        args = [cli, "app-server", "-c", _FILE_CREDENTIAL_STORE]
        for override in config_overrides:
            args += ["-c", override]
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=codex_home,
                start_new_session=True,
                limit=16 * 1024 * 1024,
            )
        except OSError as exc:
            raise CodexRpcError(f"failed to start codex app-server: {exc}") from exc
        server = cls(process, on_server_request=on_server_request)
        try:
            await server.request(
                "initialize",
                {
                    "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
                    "capabilities": {"experimentalApi": True},
                },
            )
            await server.notify("initialized")
        except BaseException:
            await server.close()
            raise
        return server

    def add_listener(self, listener: Callable[[str, Mapping[str, Any]], None]) -> Callable[[], None]:
        """登记通知监听器，返回取消登记的函数。监听器在读循环里同步调用，不能阻塞。"""
        self._listeners.append(listener)

        def remove() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return remove

    def expect_notification(
        self, method: str, predicate: Callable[[Mapping[str, Any]], bool] | None = None
    ) -> NotificationWaiter:
        """先登记、后等待：在发出会触发通知的请求之前调用，通知来得再快也不会漏掉。"""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Mapping[str, Any]] = loop.create_future()

        def listener(name: str, params: Mapping[str, Any]) -> None:
            if name == method and not future.done() and (predicate is None or predicate(params)):
                future.set_result(params)

        return NotificationWaiter(self, method, future, self.add_listener(listener))

    async def wait_for_notification(
        self,
        method: str,
        predicate: Callable[[Mapping[str, Any]], bool] | None = None,
        *,
        timeout: float,  # noqa: ASYNC109 -- 单次 JSON-RPC 等待上限，由 asyncio.wait/wait_for 实现；仓库无 trio/anyio cancel scope
    ) -> Mapping[str, Any]:
        return await self.expect_notification(method, predicate).wait(timeout=timeout)

    async def _wait_registered(
        self,
        method: str,
        future: asyncio.Future[Mapping[str, Any]],
        remove: Callable[[], None],
        *,
        timeout: float,  # noqa: ASYNC109 -- 单次 JSON-RPC 等待上限，由 asyncio.wait/wait_for 实现；仓库无 trio/anyio cancel scope
    ) -> Mapping[str, Any]:
        closed = asyncio.create_task(self._closed.wait())
        try:
            done, _ = await asyncio.wait({future, closed}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if future in done:
                return future.result()
            if closed in done:
                raise CodexRpcError("codex app-server exited")
            raise CodexRpcError(f"timed out waiting for {method}")
        finally:
            remove()
            closed.cancel()

    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,  # noqa: ASYNC109 -- 单次 JSON-RPC 等待上限，由 asyncio.wait/wait_for 实现；仓库无 trio/anyio cancel scope
    ) -> Any:
        if self._closed.is_set():
            raise CodexRpcError("codex app-server is closed")
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._write({"id": request_id, "method": method, "params": dict(params or {})})
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError as exc:
            raise CodexRpcError(f"{method} timed out") from exc
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = dict(params)
        await self._write(message)

    async def close(self) -> None:
        if self._process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._process.kill()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._process.wait(), timeout=5)
        self._closed.set()
        for task in (self._reader, self._stderr_drain):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._fail_pending(CodexRpcError("codex app-server is closed"))

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    async def _write(self, message: Mapping[str, Any]) -> None:
        stdin = self._process.stdin
        if stdin is None or stdin.is_closing():
            raise CodexRpcError("codex app-server stdin is closed")
        stdin.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
        try:
            await stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise CodexRpcError("codex app-server exited") from exc

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
                    logger.debug("codex app-server: non-JSON line ignored")
                    continue
                if isinstance(message, dict):
                    await self._dispatch(message)
        finally:
            self._closed.set()
            self._fail_pending(CodexRpcError("codex app-server exited"))

    async def _dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        message_id = message.get("id")
        if method is None and message_id is not None:
            future = self._pending.get(message_id)
            if future is None or future.done():
                return
            if "error" in message and message["error"] is not None:
                error = message["error"] or {}
                future.set_exception(
                    CodexRpcError(str(error.get("message") or "error"), code=error.get("code"), data=error.get("data"))
                )
            else:
                future.set_result(message.get("result"))
            return
        params = message.get("params") or {}
        if message_id is not None and isinstance(method, str):
            # 服务器发来的请求：在独立任务里回答，不卡住读循环
            task = asyncio.create_task(self._answer(message_id, method, params), name=f"codex-server-request-{method}")
            self._answering.add(task)
            task.add_done_callback(self._answering.discard)
            return
        if isinstance(method, str):
            for listener in list(self._listeners):
                try:
                    listener(method, params)
                except Exception:
                    logger.exception("codex app-server listener failed for %s", method)

    async def _answer(self, message_id: Any, method: str, params: Mapping[str, Any]) -> None:
        if self._on_server_request is None:
            reply: dict[str, Any] = {"id": message_id, "error": {"code": -32601, "message": f"unsupported: {method}"}}
        else:
            try:
                reply = {"id": message_id, "result": await self._on_server_request(method, params)}
            except Exception as exc:
                logger.exception("codex server request %s failed", method)
                reply = {"id": message_id, "error": {"code": -32000, "message": str(exc)}}
        with contextlib.suppress(CodexRpcError):
            await self._write(reply)

    async def _drain_stderr(self) -> None:
        stderr = self._process.stderr
        if stderr is None:
            return
        while True:
            line = await stderr.readline()
            if not line:
                return
            logger.debug("codex app-server stderr: %s", line.decode("utf-8", "replace").rstrip())

    def _fail_pending(self, error: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
