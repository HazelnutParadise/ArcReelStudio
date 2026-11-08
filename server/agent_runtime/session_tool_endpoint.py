"""内嵌 Agent 会话的本机工具端点：给只能经 HTTP 接 MCP 的引擎（Grok CLI）用的 MCP streamable HTTP 端点。

每个会话登记一组工具与一个随机令牌；引擎以 ``Authorization: Bearer <令牌>`` 呼叫 ``POST /internal/agent-tools``。
只接受本机连线，令牌只在会话存活期间有效。工具与 Codex 引擎同一份（ArcReel 工具集 + 受访问规则约束的档案工具），
执行在本进程，scope、caller 与「生成类工具等到批次终态」都与 Claude 引擎相同（docs/adr/0125）。

协定按 MCP 2025-06 的 streamable HTTP：客户端 POST 一则 JSON-RPC，服务器以 ``application/json`` 回一则响应；通知回 202。
不开 SSE 串流，GET 回 405。
"""

from __future__ import annotations

import logging
import secrets
import threading
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

#: 引擎连本机工具端点的路径（不挂在 /api/v1 之下：不走使用者会话认证，靠每会话令牌与本机限定）
SESSION_TOOL_PATH = "/internal/agent-tools"
MCP_PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "arcreel"

ToolCaller = Callable[[str, Any], Awaitable[dict[str, Any]]]
#: 工具呼叫开始前的回呼（呼叫 id、工具名、参数），引擎 client 用它写出 tool_use 帧
CallStart = Callable[[str, str, Any], None]
#: 工具呼叫完成后的回呼（呼叫 id、Codex 形状的结果），引擎 client 用它写出 tool_result 帧
CallObserver = Callable[[str, dict[str, Any]], None]

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


@dataclass
class SessionTools:
    specs: list[dict[str, Any]]
    callers: Mapping[str, ToolCaller]
    on_start: CallStart | None = None
    observer: CallObserver | None = None


class SessionToolRegistry:
    """令牌 → 一个会话的工具。进程内单例 :data:`session_tool_registry`。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionTools] = {}

    def register(self, tools: SessionTools) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = tools
        return token

    def unregister(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)

    def get(self, token: str) -> SessionTools | None:
        with self._lock:
            return self._sessions.get(token)


session_tool_registry = SessionToolRegistry()

router = APIRouter()


def _rpc_result(message_id: Any, result: Any) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": message_id, "result": result})


def _rpc_error(message_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}})


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" else ""


def to_mcp_content(result: Mapping[str, Any]) -> dict[str, Any]:
    """Codex 形状的工具结果（``contentItems`` + ``success``）→ MCP ``tools/call`` 结果。"""
    content: list[dict[str, Any]] = []
    for item in result.get("contentItems") or []:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") == "inputText":
            content.append({"type": "text", "text": str(item.get("text") or "")})
        elif item.get("type") == "inputImage":
            url = str(item.get("imageUrl") or "")
            header, _, data = url.partition(",")
            if header.startswith("data:") and ";base64" in header and data:
                content.append({"type": "image", "mimeType": header[5:].split(";", 1)[0], "data": data})
    return {"content": content, "isError": not bool(result.get("success", False))}


@router.get(SESSION_TOOL_PATH)
async def no_stream() -> Response:
    return Response(status_code=405, headers={"Allow": "POST"})


@router.post(SESSION_TOOL_PATH)
async def handle(request: Request) -> Response:
    client_host = request.client.host if request.client else ""
    if client_host not in _LOOPBACK_HOSTS:
        return Response(status_code=403)
    tools = session_tool_registry.get(_bearer(request))
    if tools is None:
        return Response(status_code=401)
    try:
        message = await request.json()
    except ValueError:
        return _rpc_error(None, -32700, "parse error")
    if not isinstance(message, dict):
        return _rpc_error(None, -32600, "batch requests are not supported")
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params") or {}
    if message_id is None:
        return Response(status_code=202)  # 通知（notifications/initialized 等）
    if method == "initialize":
        return _rpc_result(
            message_id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": "1"},
            },
        )
    if method == "ping":
        return _rpc_result(message_id, {})
    if method == "tools/list":
        listed = [
            {
                "name": spec["name"],
                "description": spec.get("description") or "",
                "inputSchema": spec.get("inputSchema") or {"type": "object"},
            }
            for spec in tools.specs
        ]
        return _rpc_result(message_id, {"tools": listed})
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        caller = tools.callers.get(name)
        if caller is None:
            return _rpc_result(
                message_id, {"content": [{"type": "text", "text": f"Tool '{name}' not found"}], "isError": True}
            )
        call_id = f"{name}-{secrets.token_hex(6)}"
        if tools.on_start is not None:
            tools.on_start(call_id, name, arguments)
        try:
            result = await caller(name, arguments)
        except Exception as exc:
            logger.exception("会话工具 %s 抛出意外异常", name)
            result = {"contentItems": [{"type": "inputText", "text": str(exc)}], "success": False}
        if tools.observer is not None:
            tools.observer(call_id, result)
        return _rpc_result(message_id, to_mcp_content(result))
    return _rpc_error(message_id, -32601, f"method not found: {method}")


__all__ = [
    "SESSION_TOOL_PATH",
    "SessionToolRegistry",
    "SessionTools",
    "router",
    "session_tool_registry",
    "to_mcp_content",
]
