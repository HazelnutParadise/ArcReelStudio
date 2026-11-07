"""多人即时协作的 WebSocket：浏览器在这里加入编辑单元的房间，收发 Yjs 同步与在线状态。

浏览器的 WebSocket 不能带请求头，所以连上后第一条消息送登录令牌（不放在网址里，免得进访问日志）。
只接受网页登录的令牌，不接受 API Key 与内嵌 Agent；之后每 ``REVALIDATE_SECONDS`` 秒（可由
``app.state.collab_revalidate_seconds`` 覆盖）在后台重新确认一次账号仍有效；停用账号、改密码或改角色后，
即使这个分页一直没有发消息，连接也会关闭。

消息都是 JSON：

- 浏览器 → 服务端：``auth``、``join`` / ``leave``（``room`` 为 ``{project, kind, key}``）、``sync`` / ``awareness``
  （``data`` 是 base64 编码的 y-protocols 消息）、``flush``（``id`` 用来对应回复）。
- 服务端 → 浏览器：``ready``、``joined``、``sync`` / ``awareness``、``status``（``saved`` / ``saving`` / ``error``）、
  ``flushed``、``removed``（单元已被删除）、``error``。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from lib.project.project_change_hints import ProjectChangeActor
from lib.project.project_manager import ProjectManager
from server.auth import API_KEY_PREFIX, EMBEDDED_AGENT_SUB, authenticate_bearer, is_auth_enabled
from server.i18n import locale_from_language_tags
from server.services.collab.hub import CollabHub
from server.services.collab.units import UnitRef

logger = logging.getLogger(__name__)

router = APIRouter(tags=["多人协作"])

AUTH_TIMEOUT_SECONDS = 10.0
REVALIDATE_SECONDS = 60.0
#: 单元键（如「剧本文件#分镜编号」）的长度上限
MAX_KEY_LENGTH = 512
#: 单条同步或在线状态消息的上限；超过的连接直接关闭
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024

#: 关闭码：认证失败、账号失效、消息不合规
CLOSE_UNAUTHORIZED = 4401
CLOSE_POLICY = 1008


class _WsConnection:
    def __init__(self, websocket: WebSocket, actor: ProjectChangeActor, locale: str) -> None:
        self.id = uuid.uuid4().hex
        self.actor = actor
        self.locale = locale
        self._ws = websocket
        self._send_lock = asyncio.Lock()

    async def send(self, message: dict[str, Any]) -> None:
        async with self._send_lock:
            await self._ws.send_json(message)


async def _authenticate(token: Any) -> ProjectChangeActor | None:
    """校验网页登录的令牌，返回改动者；不合格（含 API Key 与内嵌 Agent）时返回 None。"""
    if not is_auth_enabled():
        return {"user_id": "default", "username": "admin"}
    if not isinstance(token, str) or not token or token.startswith(API_KEY_PREFIX):
        return None
    try:
        user = await authenticate_bearer(token)
    except HTTPException:
        return None
    if user.sub == EMBEDDED_AGENT_SUB or not user.username:
        return None
    return {"user_id": user.id, "username": user.username}


def _room(message: dict[str, Any], hub: CollabHub) -> UnitRef | None:
    room = message.get("room")
    if not isinstance(room, dict):
        return None
    project, kind, key = room.get("project"), room.get("kind"), room.get("key")
    if not isinstance(project, str) or not isinstance(kind, str) or not isinstance(key, str):
        return None
    if not hub.has_kind(kind) or len(key) > MAX_KEY_LENGTH:
        return None
    try:
        ProjectManager.normalize_project_name(project)
    except ValueError:
        return None
    return UnitRef(project=project, kind=kind, key=key)


def _payload(message: dict[str, Any]) -> bytes | None:
    data = message.get("data")
    if not isinstance(data, str) or len(data) > MAX_PAYLOAD_BYTES * 4 // 3 + 4:
        return None
    try:
        return base64.b64decode(data, validate=True)
    except binascii.Error, ValueError:
        return None


@router.websocket("/collab")
async def collab_socket(websocket: WebSocket) -> None:
    hub: CollabHub = websocket.app.state.collab_hub
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), AUTH_TIMEOUT_SECONDS)
    except TimeoutError, WebSocketDisconnect, ValueError:
        await _close(websocket, CLOSE_UNAUTHORIZED)
        return
    if not isinstance(first, dict) or first.get("type") != "auth":
        await _close(websocket, CLOSE_UNAUTHORIZED)
        return
    token = first.get("token")
    actor = await _authenticate(token)
    if actor is None:
        await _close(websocket, CLOSE_UNAUTHORIZED)
        return
    language = first.get("locale")
    locale = locale_from_language_tags(language if isinstance(language, str) else "")
    conn = _WsConnection(websocket, actor, locale)
    await conn.send({"type": "ready", "user": actor})
    interval = float(getattr(websocket.app.state, "collab_revalidate_seconds", REVALIDATE_SECONDS))
    watcher = asyncio.create_task(_revalidate_periodically(websocket, token, interval))
    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                await _close(websocket, CLOSE_POLICY)
                return
            await _dispatch(hub, conn, message)
    except WebSocketDisconnect:
        pass
    except ValueError:
        # 不是 JSON
        await _close(websocket, CLOSE_POLICY)
    finally:
        watcher.cancel()
        await hub.disconnect(conn)


async def _revalidate_periodically(websocket: WebSocket, token: Any, interval: float) -> None:
    """每隔 ``interval`` 秒复核令牌；失效时关闭连接，接收循环随之结束。"""
    while True:
        await asyncio.sleep(interval)
        if await _authenticate(token) is None:
            await _close(websocket, CLOSE_UNAUTHORIZED)
            return


async def _dispatch(hub: CollabHub, conn: _WsConnection, message: dict[str, Any]) -> None:
    kind = message.get("type")
    ref = _room(message, hub)
    if ref is None:
        await conn.send({"type": "error", "code": "invalid_room"})
        return
    if kind == "join":
        await hub.join(conn, ref)
    elif kind == "leave":
        await hub.leave(conn, ref)
    elif kind in ("sync", "awareness"):
        data = _payload(message)
        if data is None:
            await conn.send({"type": "error", "code": "invalid_payload"})
            return
        if kind == "sync":
            await hub.on_sync(conn, ref, data)
        else:
            await hub.on_awareness(conn, ref, data)
    elif kind == "flush":
        request_id = message.get("id")
        await hub.flush(conn, ref, request_id if isinstance(request_id, int) else 0)
    else:
        await conn.send({"type": "error", "code": "unknown_type"})


async def _close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except RuntimeError:
        # 已经关闭
        logger.debug("协作连接已关闭", exc_info=True)
