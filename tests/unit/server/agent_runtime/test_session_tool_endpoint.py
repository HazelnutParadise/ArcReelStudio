"""本机工具端点：只认本机连线与有效令牌，照 MCP 回 initialize / tools/list / tools/call。"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from server.agent_runtime import session_tool_endpoint
from server.agent_runtime.session_tool_endpoint import (
    SESSION_TOOL_PATH,
    SessionToolRegistry,
    SessionTools,
    router,
    to_mcp_content,
)


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> SessionToolRegistry:
    fresh = SessionToolRegistry()
    monkeypatch.setattr(session_tool_endpoint, "session_tool_registry", fresh)
    return fresh


def _client(host: str = "127.0.0.1") -> AsyncClient:
    app = FastAPI()
    app.include_router(router)
    return AsyncClient(transport=ASGITransport(app=app, client=(host, 5000)), base_url="http://t")


def _tools(events: list[Any]) -> SessionTools:
    async def caller(tool: str, arguments: Any) -> dict[str, Any]:
        return {"contentItems": [{"type": "inputText", "text": f"ran {tool}"}], "success": True}

    return SessionTools(
        specs=[{"name": "list_projects", "description": "d", "inputSchema": {"type": "object"}}],
        callers={"list_projects": caller},
        on_start=lambda call_id, name, args: events.append(("start", call_id, name, args)),
        observer=lambda call_id, result: events.append(("done", call_id, result["success"])),
    )


def _rpc(method: str, params: dict[str, Any] | None = None, message_id: int | None = 1) -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if message_id is not None:
        body["id"] = message_id
    return body


async def test_calls_need_a_registered_token(registry: SessionToolRegistry) -> None:
    async with _client() as client:
        assert (await client.post(SESSION_TOOL_PATH, json=_rpc("tools/list"))).status_code == 401
        bad = await client.post(SESSION_TOOL_PATH, json=_rpc("tools/list"), headers={"Authorization": "Bearer nope"})
        assert bad.status_code == 401


async def test_only_loopback_clients_are_served(registry: SessionToolRegistry) -> None:
    token = registry.register(_tools([]))
    async with _client(host="10.0.0.5") as client:
        response = await client.post(
            SESSION_TOOL_PATH, json=_rpc("tools/list"), headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 403


async def test_initialize_list_and_call(registry: SessionToolRegistry) -> None:
    events: list[Any] = []
    token = registry.register(_tools(events))
    headers = {"Authorization": f"Bearer {token}"}
    async with _client() as client:
        init = (await client.post(SESSION_TOOL_PATH, json=_rpc("initialize"), headers=headers)).json()
        note = await client.post(
            SESSION_TOOL_PATH, json=_rpc("notifications/initialized", message_id=None), headers=headers
        )
        listed = (await client.post(SESSION_TOOL_PATH, json=_rpc("tools/list"), headers=headers)).json()
        called = (
            await client.post(
                SESSION_TOOL_PATH,
                json=_rpc("tools/call", {"name": "list_projects", "arguments": {"x": 1}}),
                headers=headers,
            )
        ).json()
        missing = (
            await client.post(SESSION_TOOL_PATH, json=_rpc("tools/call", {"name": "rm_rf"}), headers=headers)
        ).json()
        unknown = (await client.post(SESSION_TOOL_PATH, json=_rpc("resources/list"), headers=headers)).json()
        stream = await client.get(SESSION_TOOL_PATH, headers=headers)

    assert init["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert note.status_code == 202
    assert [tool["name"] for tool in listed["result"]["tools"]] == ["list_projects"]
    assert called["result"] == {"content": [{"type": "text", "text": "ran list_projects"}], "isError": False}
    assert missing["result"]["isError"] is True
    assert unknown["error"]["code"] == -32601
    assert stream.status_code == 405
    (start, done) = events
    assert start[0] == "start"
    assert start[2:] == ("list_projects", {"x": 1})
    assert done == ("done", start[1], True)


async def test_unregistered_tokens_stop_working(registry: SessionToolRegistry) -> None:
    token = registry.register(_tools([]))
    registry.unregister(token)
    async with _client() as client:
        response = await client.post(
            SESSION_TOOL_PATH, json=_rpc("tools/list"), headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 401


def test_images_become_mcp_image_blocks() -> None:
    result = {
        "contentItems": [
            {"type": "inputText", "text": "see"},
            {"type": "inputImage", "imageUrl": "data:image/png;base64,UE5H"},
            {"type": "inputImage", "imageUrl": "https://example.com/x.png"},
        ],
        "success": False,
    }
    assert to_mcp_content(result) == {
        "content": [{"type": "text", "text": "see"}, {"type": "image", "mimeType": "image/png", "data": "UE5H"}],
        "isError": True,
    }
