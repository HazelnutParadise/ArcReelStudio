"""协作中枢：每个正在被编辑的单元一个房间，转发 Yjs 同步与在线状态，合并后写回项目文件。

- **同步**：浏览器用标准的 y-protocols 消息（sync step1/step2/update 与 awareness）。服务端持有每个房间的文档，
  收到某个连接的更新就套进文档并转发给房间里的其他连接。
- **写回**：文档有改动后，安静 ``debounce`` 秒（最长 ``max_wait`` 秒）就把改过的顶层字段写回项目文件，
  变更来源记为 ``collab``、改动者记为最近一位改动的成员。写回失败（内容不合规）时把原因告诉房间里的每个人。
- **外部改动**：Agent、后台任务或其他接口改了同一个单元时，从「上次与存储一致时的文档状态」出发套上新内容算出
  差异，再合并进当前文档。正在打、还没写回的字因此不会被覆盖，由 CRDT 与外部改动合并。
- **收尾**：最后一个人离开后等 ``close_grace`` 秒（给刷新页面、断线重连留时间），写回并关闭房间。
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol

from pycrdt import (
    Awareness,
    Doc,
    YMessageType,
    YSyncMessageType,
    create_awareness_message,
    create_sync_message,
    create_update_message,
    handle_sync_message,
    read_message,
)

from lib.collab.ydoc_json import apply_json, new_unit_doc, unit_json
from lib.infra.async_thread import run_sync_transaction
from lib.project.project_change_hints import ProjectChangeActor, project_change_actor, project_change_source
from lib.project.project_manager import ProjectManager
from server.services.collab.units import UnitNotFoundError, UnitRef, UnitSpec, UnitWriteError

logger = logging.getLogger(__name__)

_EMPTY_UPDATE = b"\x00\x00"

ChangeStream = Callable[[str], AbstractAsyncContextManager[AsyncIterator[Any]]]
ErrorText = Callable[[str, str], str]


class Connection(Protocol):
    """一个浏览器连接；同一个连接可以同时在好几个房间里。"""

    id: str
    actor: ProjectChangeActor
    locale: str

    async def send(self, message: dict[str, Any]) -> None: ...


@dataclass
class Room:
    ref: UnitRef
    doc: Doc
    awareness: Awareness
    #: 存储里的内容（最近一次读到或写入后读回的）
    stored: dict[str, Any]
    #: 文档与存储一致时的文档状态，外部改动从这里出发算差异
    base_update: bytes
    #: 最近一次写回时文档里各字段的值，用来找出之后改过的字段
    sent: dict[str, Any]
    members: dict[str, Connection] = field(default_factory=dict)
    awareness_ids: dict[str, set[int]] = field(default_factory=dict)
    last_actor: ProjectChangeActor | None = None
    dirty: bool = False
    first_dirty_at: float = 0.0
    last_change_at: float = 0.0
    error: dict[str, str] | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    persist_task: asyncio.Task | None = None
    close_task: asyncio.Task | None = None
    closed: bool = False


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class CollabHub:
    def __init__(
        self,
        pm: ProjectManager,
        specs: dict[str, UnitSpec],
        change_stream: ChangeStream,
        *,
        error_text: ErrorText,
        debounce: float = 0.8,
        max_wait: float = 3.0,
        close_grace: float = 5.0,
    ) -> None:
        self._pm = pm
        self._specs = specs
        self._change_stream = change_stream
        self._error_text = error_text
        self._debounce = debounce
        self._max_wait = max_wait
        self._close_grace = close_grace
        self._rooms: dict[UnitRef, Room] = {}
        self._room_locks: dict[UnitRef, asyncio.Lock] = {}
        self._watchers: dict[str, asyncio.Task] = {}

    def has_kind(self, kind: str) -> bool:
        return kind in self._specs

    # ── 连接进出 ─────────────────────────────────────────────────

    async def join(self, conn: Connection, ref: UnitRef) -> None:
        room = await self._get_or_open(ref)
        if room is None:
            await conn.send({"type": "removed", "room": _room_id(ref), "reason": "not_found"})
            return
        if room.close_task is not None:
            room.close_task.cancel()
            room.close_task = None
        room.members[conn.id] = conn
        room.awareness_ids.setdefault(conn.id, set())
        room_id = _room_id(ref)
        await conn.send({"type": "joined", "room": room_id})
        # 先给出服务端的状态向量，浏览器回送它离线期间的改动；浏览器的 step1 由它自己发起
        await conn.send({"type": "sync", "room": room_id, "data": _b64(create_sync_message(room.doc))})
        states = list(room.awareness.states)
        if states:
            await conn.send(
                {
                    "type": "awareness",
                    "room": room_id,
                    "data": _b64(create_awareness_message(room.awareness.encode_awareness_update(states))),
                }
            )
        await conn.send(self._status_message(room, conn))

    async def leave(self, conn: Connection, ref: UnitRef) -> None:
        room = self._rooms.get(ref)
        if room is None or conn.id not in room.members:
            return
        del room.members[conn.id]
        ids = room.awareness_ids.pop(conn.id, set())
        if ids:
            room.awareness.remove_awareness_states(list(ids), origin=conn.id)
            message = create_awareness_message(room.awareness.encode_awareness_update(list(ids)))
            await self._broadcast(room, {"type": "awareness", "room": _room_id(ref), "data": _b64(message)})
        if not room.members:
            room.close_task = asyncio.create_task(self._close_later(room), name=f"collab-close-{ref.kind}")

    async def disconnect(self, conn: Connection) -> None:
        for ref in [ref for ref, room in self._rooms.items() if conn.id in room.members]:
            await self.leave(conn, ref)

    # ── 消息 ─────────────────────────────────────────────────────

    async def on_sync(self, conn: Connection, ref: UnitRef, data: bytes) -> None:
        room = self._member_room(conn, ref)
        if room is None or not data or data[0] != YMessageType.SYNC:
            return
        message = data[1:]
        if not message:
            return
        if message[0] == YSyncMessageType.SYNC_STEP1:
            reply = handle_sync_message(message, room.doc)
            if reply is not None:
                await conn.send({"type": "sync", "room": _room_id(ref), "data": _b64(reply)})
            return
        before = room.doc.get_state()
        handle_sync_message(message, room.doc)
        update = room.doc.get_update(before)
        if update == _EMPTY_UPDATE:
            return
        await self._broadcast(
            room, {"type": "sync", "room": _room_id(ref), "data": _b64(create_update_message(update))}, exclude=conn.id
        )
        self._mark_dirty(room, conn.actor)

    async def on_awareness(self, conn: Connection, ref: UnitRef, data: bytes) -> None:
        room = self._member_room(conn, ref)
        if room is None or not data or data[0] != YMessageType.AWARENESS:
            return
        update = read_message(data[1:])
        before = set(room.awareness.states)
        room.awareness.apply_awareness_update(update, origin=conn.id)
        added = set(room.awareness.states) - before
        room.awareness_ids[conn.id].update(added)
        await self._broadcast(room, {"type": "awareness", "room": _room_id(ref), "data": _b64(data)}, exclude=conn.id)

    async def flush(self, conn: Connection, ref: UnitRef, request_id: int) -> None:
        room = self._member_room(conn, ref)
        if room is None:
            await conn.send({"type": "flushed", "room": _room_id(ref), "id": request_id, "ok": False})
            return
        await self._persist(room)
        await conn.send({"type": "flushed", "room": _room_id(ref), "id": request_id, "ok": room.error is None})

    async def shutdown(self) -> None:
        for room in list(self._rooms.values()):
            if room.persist_task is not None:
                room.persist_task.cancel()
            if room.close_task is not None:
                room.close_task.cancel()
            await self._persist(room)
            room.closed = True
        self._rooms.clear()
        for task in self._watchers.values():
            task.cancel()
        await asyncio.gather(*self._watchers.values(), return_exceptions=True)
        self._watchers.clear()

    # ── 房间生命周期 ─────────────────────────────────────────────

    async def _get_or_open(self, ref: UnitRef) -> Room | None:
        room = self._rooms.get(ref)
        if room is not None:
            return room
        lock = self._room_locks.setdefault(ref, asyncio.Lock())
        async with lock:
            room = self._rooms.get(ref)
            if room is not None:
                return room
            spec = self._specs[ref.kind]
            try:
                stored = await run_sync_transaction(spec.read, self._pm, ref.project, ref.key)
            except UnitNotFoundError:
                return None
            doc = new_unit_doc(stored)
            awareness = Awareness(doc)
            # 服务端不是房间里的成员，不广播自己的在线状态
            awareness.set_local_state(None)
            room = Room(
                ref=ref,
                doc=doc,
                awareness=awareness,
                stored=stored,
                base_update=doc.get_update(),
                sent=dict(stored),
            )
            self._rooms[ref] = room
            self._ensure_watch(ref.project)
            return room

    async def _close_later(self, room: Room) -> None:
        try:
            await asyncio.sleep(self._close_grace)
        except asyncio.CancelledError:
            return
        if room.members:
            return
        if room.persist_task is not None:
            room.persist_task.cancel()
        await self._persist(room)
        if room.members:
            return
        room.closed = True
        self._rooms.pop(room.ref, None)
        self._room_locks.pop(room.ref, None)
        if not any(ref.project == room.ref.project for ref in self._rooms):
            watcher = self._watchers.pop(room.ref.project, None)
            if watcher is not None:
                watcher.cancel()

    def _member_room(self, conn: Connection, ref: UnitRef) -> Room | None:
        room = self._rooms.get(ref)
        if room is None or room.closed or conn.id not in room.members:
            return None
        return room

    # ── 写回 ─────────────────────────────────────────────────────

    def _mark_dirty(self, room: Room, actor: ProjectChangeActor) -> None:
        now = time.monotonic()
        if not room.dirty:
            room.dirty = True
            room.first_dirty_at = now
        room.last_change_at = now
        room.last_actor = actor
        if room.persist_task is None or room.persist_task.done():
            room.persist_task = asyncio.create_task(self._persist_when_quiet(room), name=f"collab-save-{room.ref.kind}")

    async def _persist_when_quiet(self, room: Room) -> None:
        while room.dirty and not room.closed:
            now = time.monotonic()
            due = min(room.last_change_at + self._debounce, room.first_dirty_at + self._max_wait)
            if now < due:
                await asyncio.sleep(due - now)
                continue
            await self._persist(room)

    async def _persist(self, room: Room) -> None:
        async with room.lock:
            room.dirty = False
            current = unit_json(room.doc)
            snapshot = room.doc.get_update()
            changes = {key: value for key, value in current.items() if room.sent.get(key) != value}
            if not changes:
                return
            spec = self._specs[room.ref.kind]
            actor = room.last_actor
            await self._broadcast(room, {"type": "status", "room": _room_id(room.ref), "state": "saving"})
            try:
                stored = await run_sync_transaction(self._write_and_read, spec, room.ref, changes, actor)
            except UnitNotFoundError:
                await self._remove(room, "not_found")
                return
            except UnitWriteError as exc:
                room.error = {"code": exc.code, "detail": exc.detail}
                logger.info("协作内容写回被拒绝 kind=%s code=%s", room.ref.kind, exc.code)
                await self._broadcast_status(room)
                return
            except Exception:
                room.error = {"code": "save_failed", "detail": ""}
                logger.exception("协作内容写回失败 kind=%s project=%s", room.ref.kind, room.ref.project)
                await self._broadcast_status(room)
                return
            room.error = None
            room.sent = current
            room.base_update = snapshot
            room.stored = stored
            await self._broadcast_status(room)

    def _write_and_read(
        self, spec: UnitSpec, ref: UnitRef, changes: dict[str, Any], actor: ProjectChangeActor | None
    ) -> dict[str, Any]:
        with project_change_source("collab"), project_change_actor(actor):
            spec.write(self._pm, ref.project, ref.key, changes)
        return spec.read(self._pm, ref.project, ref.key)

    # ── 外部改动 ─────────────────────────────────────────────────

    def _ensure_watch(self, project: str) -> None:
        task = self._watchers.get(project)
        if task is not None and not task.done():
            return
        self._watchers[project] = asyncio.create_task(self._watch(project), name=f"collab-watch-{project}")

    async def _watch(self, project: str) -> None:
        try:
            async with self._change_stream(project) as stream:
                async for item in stream:
                    # 订阅建立后的第一份快照也重读一次：房间打开（读内容）到订阅生效之间的改动不会漏掉
                    if isinstance(item, tuple) and item and item[0] in ("snapshot", "changes"):
                        await self.refresh_project(project)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("协作房间订阅项目变更失败 project=%s", project)

    async def refresh_project(self, project: str) -> None:
        """重读这个项目里所有打开的单元，把存储里的新内容合并进文档。"""
        for room in [room for ref, room in self._rooms.items() if ref.project == project]:
            await self._refresh_room(room)

    async def _refresh_room(self, room: Room) -> None:
        async with room.lock:
            spec = self._specs[room.ref.kind]
            try:
                latest = await run_sync_transaction(spec.read, self._pm, room.ref.project, room.ref.key)
            except UnitNotFoundError:
                await self._remove(room, "not_found")
                return
            changed = [key for key, value in latest.items() if room.stored.get(key) != value]
            if not changed:
                return
            # 从上次与存储一致的状态出发套上外部的新内容，得到「外部改了什么」的增量，再合并进当前文档
            base = Doc()
            base.apply_update(room.base_update)
            base_state = base.get_state()
            target = {**unit_json(base), **{key: latest[key] for key in changed}}
            apply_json(base, target)
            delta = base.get_update(base_state)
            before = room.doc.get_state()
            room.doc.apply_update(delta)
            update = room.doc.get_update(before)
            room.stored = latest
            room.base_update = base.get_update()
            room.sent = {**room.sent, **{key: latest[key] for key in changed}}
            if update != _EMPTY_UPDATE:
                await self._broadcast(
                    room, {"type": "sync", "room": _room_id(room.ref), "data": _b64(create_update_message(update))}
                )
            # 合并后文档里还有没写回的字（别人正在打的）时照常写回
            if unit_json(room.doc) != {**room.sent}:
                room.dirty = True
                room.first_dirty_at = room.last_change_at = time.monotonic()
                if room.persist_task is None or room.persist_task.done():
                    room.persist_task = asyncio.create_task(self._persist_when_quiet(room))

    async def _remove(self, room: Room, reason: str) -> None:
        room.closed = True
        self._rooms.pop(room.ref, None)
        await self._broadcast(room, {"type": "removed", "room": _room_id(room.ref), "reason": reason})
        room.members.clear()

    # ── 发送 ─────────────────────────────────────────────────────

    def _status_message(self, room: Room, conn: Connection) -> dict[str, Any]:
        message: dict[str, Any] = {
            "type": "status",
            "room": _room_id(room.ref),
            "state": "error" if room.error is not None else "saved",
        }
        if room.error is not None:
            message["error"] = {
                "code": room.error["code"],
                "message": self._error_text(room.error["code"], conn.locale),
            }
        return message

    async def _broadcast_status(self, room: Room) -> None:
        for conn in list(room.members.values()):
            with contextlib.suppress(Exception):
                await conn.send(self._status_message(room, conn))

    async def _broadcast(self, room: Room, message: dict[str, Any], *, exclude: str | None = None) -> None:
        for conn_id, conn in list(room.members.items()):
            if conn_id == exclude:
                continue
            try:
                await conn.send(message)
            except Exception:
                logger.debug("协作消息发送失败 conn=%s", conn_id, exc_info=True)


def _room_id(ref: UnitRef) -> dict[str, str]:
    return {"project": ref.project, "kind": ref.kind, "key": ref.key}


def create_collab_hub(project_events: Any) -> CollabHub:
    """按应用的单例组装中枢：项目文件经全局 ``ProjectManager`` 读写，外部改动来自项目事件流。"""
    from lib.i18n import _
    from lib.project.project_manager import get_project_manager
    from server.services.collab.units import UNIT_SPECS

    def error_text(code: str, locale: str) -> str:
        return _(f"collab_error_{code}", locale=locale)

    return CollabHub(get_project_manager(), UNIT_SPECS, project_events.stream_events, error_text=error_text)
