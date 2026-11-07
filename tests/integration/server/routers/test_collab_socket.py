"""协作 WebSocket：先认证再加入房间，只接受网页登录，打字经房间写回项目文件。"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pycrdt import Doc, Map, YMessageType, create_sync_message, create_update_message, handle_sync_message
from starlette.websockets import WebSocketDisconnect

from lib.collab.ydoc_json import ROOT, unit_json
from lib.project.project_manager import ProjectManager
from server.auth import CurrentUserInfo
from server.routers import collab
from server.services.collab.hub import CollabHub
from server.services.collab.units import UNIT_SPECS

ROOM = {"project": "demo", "kind": "overview", "key": ""}


def _users(token: str) -> CurrentUserInfo:
    known = {
        "alice-token": CurrentUserInfo(id="u1", sub="alice", role="user", username="alice"),
        "agent-token": CurrentUserInfo(id="default", sub="embedded-agent", role="user"),
    }
    if token not in known:
        raise HTTPException(status_code=401, detail="bad token")
    return known[token]


@pytest.fixture
def socket_project_files(tmp_path) -> ProjectManager:
    manager = ProjectManager(tmp_path / "projects")
    manager.create_project("demo")
    manager.update_project("demo", lambda data: data.update({"overview": {"synopsis": "雨夜"}}))
    return manager


@pytest.fixture
def socket_client(socket_project_files, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")

    async def _authenticate(token: str) -> CurrentUserInfo:
        return _users(token)

    monkeypatch.setattr(collab, "authenticate_bearer", _authenticate)

    @contextlib.asynccontextmanager
    async def _no_changes(_project: str):
        async def _iter() -> AsyncIterator[object]:
            yield ("snapshot", {})
            while True:
                await asyncio.sleep(3600)
                yield ("noop", {})

        yield _iter()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.collab_hub = CollabHub(
            socket_project_files,
            UNIT_SPECS,
            _no_changes,
            error_text=lambda code, _detail, _l, _params: code,
            debounce=0.05,
            max_wait=0.2,
        )
        app.state.collab_revalidate_seconds = 0.05
        yield
        await app.state.collab_hub.shutdown()

    app = FastAPI(lifespan=lifespan)
    app.include_router(collab.router, prefix="/api/v1")
    with TestClient(app) as test_client:
        yield test_client


def _receive_until(ws, message_type: str) -> dict:
    while True:
        message = ws.receive_json()
        if message["type"] == message_type:
            return message


def test_a_bad_token_closes_the_connection(socket_client) -> None:
    with socket_client.websocket_connect("/api/v1/collab") as ws:
        ws.send_json({"type": "auth", "token": "nope"})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == collab.CLOSE_UNAUTHORIZED


@pytest.mark.parametrize("token", ["arc-some-api-key", "agent-token"])
def test_api_keys_and_the_embedded_agent_are_refused(socket_client, token) -> None:
    with socket_client.websocket_connect("/api/v1/collab") as ws:
        ws.send_json({"type": "auth", "token": token})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == collab.CLOSE_UNAUTHORIZED


def test_the_first_message_must_authenticate(socket_client) -> None:
    with socket_client.websocket_connect("/api/v1/collab") as ws:
        ws.send_json({"type": "join", "room": ROOM})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == collab.CLOSE_UNAUTHORIZED


def test_typing_is_written_back(socket_client, socket_project_files) -> None:
    doc = Doc()
    with socket_client.websocket_connect("/api/v1/collab") as ws:
        ws.send_json({"type": "auth", "token": "alice-token", "locale": "zh-TW"})
        assert ws.receive_json() == {"type": "ready", "user": {"user_id": "u1", "username": "alice"}}
        ws.send_json({"type": "join", "room": ROOM})
        assert _receive_until(ws, "joined")["room"] == ROOM
        ws.send_json({"type": "sync", "room": ROOM, "data": base64.b64encode(create_sync_message(doc)).decode()})
        while unit_json(doc).get("synopsis") is None:
            message = _receive_until(ws, "sync")
            data = base64.b64decode(message["data"])
            assert data[0] == YMessageType.SYNC
            handle_sync_message(data[1:], doc)
        assert unit_json(doc)["synopsis"] == "雨夜"

        before = doc.get_state()
        doc.get(ROOT, type=Map)["synopsis"].insert(0, "深夜，")
        update = create_update_message(doc.get_update(before))
        ws.send_json({"type": "sync", "room": ROOM, "data": base64.b64encode(update).decode()})
        ws.send_json({"type": "flush", "room": ROOM, "id": 1})
        flushed = _receive_until(ws, "flushed")

    assert flushed == {"type": "flushed", "room": ROOM, "id": 1, "ok": True}
    assert socket_project_files.load_project("demo")["overview"]["synopsis"] == "深夜，雨夜"


def test_unknown_rooms_and_bad_payloads_are_answered_with_errors(socket_client) -> None:
    with socket_client.websocket_connect("/api/v1/collab") as ws:
        ws.send_json({"type": "auth", "token": "alice-token"})
        ws.receive_json()
        ws.send_json({"type": "join", "room": {"project": "demo", "kind": "nope", "key": ""}})
        assert ws.receive_json() == {"type": "error", "code": "invalid_room"}
        ws.send_json({"type": "join", "room": {"project": "../etc", "kind": "overview", "key": ""}})
        assert ws.receive_json() == {"type": "error", "code": "invalid_room"}
        ws.send_json({"type": "sync", "room": ROOM, "data": "%%%"})
        assert ws.receive_json() == {"type": "error", "code": "invalid_payload"}


def test_an_idle_connection_is_closed_once_the_account_becomes_invalid(socket_client, monkeypatch) -> None:
    with socket_client.websocket_connect("/api/v1/collab") as ws:
        ws.send_json({"type": "auth", "token": "alice-token"})
        ws.receive_json()

        async def _revoked(_token: str) -> CurrentUserInfo:
            raise HTTPException(status_code=401, detail="revoked")

        monkeypatch.setattr(collab, "authenticate_bearer", _revoked)
        # 不再发任何消息：后台复核也要把连接关掉
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == collab.CLOSE_UNAUTHORIZED
