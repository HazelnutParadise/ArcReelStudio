"""协作中枢：两位成员同时编辑同一单元，合并、转发、写回，以及外部改动并入正在打的字。

浏览器一侧用 pycrdt 文档模拟（与 Yjs 互通），项目文件是真的，变更推送用可控的替身。
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from pycrdt import Doc, Map, YMessageType, create_sync_message, create_update_message, handle_sync_message

from lib.collab.ydoc_json import ROOT, unit_json
from lib.project.project_manager import ProjectManager
from server.services.collab.hub import CollabHub
from server.services.collab.units import UNIT_SPECS, UnitRef, UnitWriteError

PROJECT = "demo"
REF = UnitRef(project=PROJECT, kind="overview", key="")


class FakeConn:
    """一个浏览器分页：把服务端发来的同步消息套进自己的文档。"""

    def __init__(self, conn_id: str, username: str) -> None:
        self.id = conn_id
        self.actor = {"user_id": f"u-{username}", "username": username}
        self.locale = "zh-TW"
        self.doc = Doc()
        self.messages: list[dict[str, Any]] = []
        self._arrived = asyncio.Event()

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        if message["type"] == "sync":
            data = base64.b64decode(message["data"])
            assert data[0] == YMessageType.SYNC
            handle_sync_message(data[1:], self.doc)
        self._arrived.set()

    async def until(self, condition: Callable[[], bool]) -> None:
        """等到 ``condition`` 成立：每收到一条服务端消息重新判断一次。"""
        while not condition():
            self._arrived.clear()
            await self._arrived.wait()

    async def written_back(self, count: int = 1) -> None:
        """等到房间完成 ``count`` 次写回：每次写回先广播 saving，写完读回（或被拒）后再广播 saved / error。"""
        await self.until(lambda: self._write_backs() >= count)

    def _write_backs(self) -> int:
        done, saving = 0, False
        for state in (m["state"] for m in self.statuses()):
            if state == "saving":
                saving = True
            elif saving:
                done, saving = done + 1, False
        return done

    def text(self, field: str) -> str:
        return unit_json(self.doc)[field]

    def type_into(self, field: str, index: int, value: str) -> bytes:
        """在 ``field`` 的第 ``index`` 个 UTF-8 字节处打字，返回要送给服务端的更新消息。"""
        before = self.doc.get_state()
        self.doc.get(ROOT, type=Map)[field].insert(index, value)
        return create_update_message(self.doc.get_update(before))

    def statuses(self) -> list[dict[str, Any]]:
        return [m for m in self.messages if m["type"] == "status"]


class ManualChanges:
    """项目变更推送的替身：测试里手动推一条「有变更」。"""

    def __init__(self) -> None:
        self.queues: dict[str, asyncio.Queue] = {}
        self._subscribed: dict[str, asyncio.Event] = {}

    @contextlib.asynccontextmanager
    async def __call__(self, project: str):
        queue: asyncio.Queue = asyncio.Queue()
        self.queues[project] = queue
        self._subscription(project).set()

        async def _iter() -> AsyncIterator[Any]:
            # 与真实的项目事件流一样，先给出一份快照
            yield ("snapshot", {})
            while True:
                yield await queue.get()

        yield _iter()

    def push(self, project: str) -> None:
        self.queues[project].put_nowait(("changes", {"source": "worker"}))

    async def subscribed(self, project: str) -> None:
        """等到房间订阅了 ``project`` 的变更推送。"""
        await self._subscription(project).wait()

    def _subscription(self, project: str) -> asyncio.Event:
        return self._subscribed.setdefault(project, asyncio.Event())


async def test_a_change_made_before_the_subscription_is_ready_is_not_missed(hub, hub_project_files) -> None:
    alice = FakeConn("c1", "alice")
    await _join(hub, alice)
    # 房间已经读了内容，但订阅还没生效时就有人改了文件
    hub_project_files.update_project(PROJECT, lambda data: data["overview"].update({"genre": "科幻"}))

    # 订阅生效时的快照触发一次重读，改动随之送到
    await alice.until(lambda: alice.text("genre") != "悬疑")
    assert alice.text("genre") == "科幻"


@pytest.fixture
def hub_project_files(tmp_path) -> ProjectManager:
    manager = ProjectManager(tmp_path / "projects")
    manager.create_project(PROJECT)
    manager.update_project(PROJECT, lambda data: data.update({"overview": {"synopsis": "雨夜", "genre": "悬疑"}}))
    return manager


@pytest.fixture
def changes() -> ManualChanges:
    return ManualChanges()


@pytest.fixture
async def hub(hub_project_files, changes):
    instance = CollabHub(
        hub_project_files,
        UNIT_SPECS,
        changes,
        error_text=lambda code, _detail, locale, _params: f"[{locale}] {code}",
        debounce=0.05,
        max_wait=0.2,
        close_grace=0.05,
    )
    yield instance
    await instance.shutdown()


async def _join(hub: CollabHub, conn: FakeConn) -> None:
    await hub.join(conn, REF)
    # 浏览器发起自己的 step1，拿到完整内容
    await hub.on_sync(conn, REF, create_sync_message(conn.doc))


async def test_joining_delivers_the_stored_content(hub) -> None:
    alice = FakeConn("c1", "alice")

    await _join(hub, alice)

    assert alice.messages[0]["type"] == "joined"
    assert alice.text("synopsis") == "雨夜"
    assert alice.text("world_setting") == ""
    assert alice.statuses()[-1]["state"] == "saved"


async def test_typing_reaches_the_other_member_and_is_written_back(hub, hub_project_files) -> None:
    alice, bob = FakeConn("c1", "alice"), FakeConn("c2", "bob")
    await _join(hub, alice)
    await _join(hub, bob)

    await hub.on_sync(alice, REF, alice.type_into("synopsis", len("雨夜".encode()), "，街口"))

    # 转发在 on_sync 里同步完成；写回是之后的防抖任务，以它结束时广播的状态为准
    assert bob.text("synopsis") == "雨夜，街口"
    await alice.written_back()
    assert hub_project_files.load_project(PROJECT)["overview"]["synopsis"] == "雨夜，街口"


async def test_simultaneous_typing_in_the_same_field_keeps_both(hub, hub_project_files) -> None:
    alice, bob = FakeConn("c1", "alice"), FakeConn("c2", "bob")
    await _join(hub, alice)
    await _join(hub, bob)

    # 两人在同一刻、基于同一份内容打字：Alice 在开头，Bob 在结尾
    from_alice = alice.type_into("synopsis", 0, "深夜，")
    from_bob = bob.type_into("synopsis", len("雨夜".encode()), "的街口")
    await hub.on_sync(alice, REF, from_alice)
    await hub.on_sync(bob, REF, from_bob)
    await alice.written_back()

    assert alice.text("synopsis") == bob.text("synopsis") == "深夜，雨夜的街口"
    assert hub_project_files.load_project(PROJECT)["overview"]["synopsis"] == "深夜，雨夜的街口"


async def test_external_change_merges_with_unsaved_typing(hub, hub_project_files, changes) -> None:
    alice = FakeConn("c1", "alice")
    await _join(hub, alice)
    await changes.subscribed(PROJECT)

    # Alice 在开头打了字、还没写回；同时 Agent 改了文件，在结尾加了字
    await hub.on_sync(alice, REF, alice.type_into("synopsis", 0, "深夜，"))
    hub_project_files.update_project(PROJECT, lambda data: data["overview"].update({"synopsis": "雨夜。"}))
    changes.push(PROJECT)
    # 重读先拿到房间锁，合并后的内容随防抖写回落盘
    await alice.written_back()

    assert alice.text("synopsis") == "深夜，雨夜。"
    assert hub_project_files.load_project(PROJECT)["overview"]["synopsis"] == "深夜，雨夜。"


async def test_external_change_to_another_field_does_not_touch_the_typed_one(hub, hub_project_files, changes) -> None:
    alice = FakeConn("c1", "alice")
    await _join(hub, alice)
    await changes.subscribed(PROJECT)

    hub_project_files.update_project(PROJECT, lambda data: data["overview"].update({"genre": "爱情"}))
    changes.push(PROJECT)

    await alice.until(lambda: alice.text("genre") != "悬疑")
    assert alice.text("genre") == "爱情"
    assert alice.text("synopsis") == "雨夜"


async def test_written_back_text_is_trimmed_but_the_typist_keeps_the_space(hub, hub_project_files) -> None:
    alice = FakeConn("c1", "alice")
    await _join(hub, alice)

    await hub.on_sync(alice, REF, alice.type_into("synopsis", len("雨夜".encode()), " "))
    await alice.written_back()

    assert hub_project_files.load_project(PROJECT)["overview"]["synopsis"] == "雨夜"
    # 正在打字的人刚打的空格不会被收回
    assert alice.text("synopsis") == "雨夜 "


async def test_a_rejected_write_is_reported_to_everyone_in_the_room(hub, monkeypatch) -> None:
    alice, bob = FakeConn("c1", "alice"), FakeConn("c2", "bob")
    await _join(hub, alice)
    await _join(hub, bob)

    def _reject(*_args, **_kwargs):
        raise UnitWriteError("overview_invalid", "bad")

    monkeypatch.setattr(UNIT_SPECS["overview"], "write", _reject)
    await hub.on_sync(alice, REF, alice.type_into("synopsis", 0, "x"))
    # 状态在同一轮里依次发给每位成员，Alice 收到时 Bob 也已收到
    await alice.written_back()

    for conn in (alice, bob):
        last = conn.statuses()[-1]
        assert last["state"] == "error"
        assert last["error"] == {"code": "overview_invalid", "message": "[zh-TW] overview_invalid"}


async def test_flush_writes_immediately(hub, hub_project_files) -> None:
    alice = FakeConn("c1", "alice")
    await _join(hub, alice)
    await hub.on_sync(alice, REF, alice.type_into("synopsis", 0, "先存："))

    await hub.flush(alice, REF, 7)

    assert hub_project_files.load_project(PROJECT)["overview"]["synopsis"] == "先存：雨夜"
    assert alice.messages[-1] == {
        "type": "flushed",
        "room": {"project": PROJECT, "kind": "overview", "key": ""},
        "id": 7,
        "ok": True,
    }


async def test_leaving_writes_back_and_closes_the_room(hub, hub_project_files) -> None:
    alice = FakeConn("c1", "alice")
    await _join(hub, alice)
    await hub.on_sync(alice, REF, alice.type_into("synopsis", 0, "离开前"))

    await hub.leave(alice, REF)
    # 最后一位成员离开后，关闭任务写回并移除房间
    close_task = hub._rooms[REF].close_task
    assert close_task is not None
    await close_task

    assert hub_project_files.load_project(PROJECT)["overview"]["synopsis"] == "离开前雨夜"
    assert REF not in hub._rooms


async def test_a_member_who_left_receives_nothing_more(hub) -> None:
    alice, bob = FakeConn("c1", "alice"), FakeConn("c2", "bob")
    await _join(hub, alice)
    await _join(hub, bob)
    await hub.leave(bob, REF)
    count = len(bob.messages)

    await hub.on_sync(alice, REF, alice.type_into("synopsis", 0, "x"))

    assert len(bob.messages) == count


async def test_a_missing_unit_is_reported_as_removed(hub, hub_project_files) -> None:
    alice = FakeConn("c1", "alice")

    await hub.join(alice, UnitRef(project="nope", kind="overview", key=""))

    assert alice.messages == [
        {"type": "removed", "room": {"project": "nope", "kind": "overview", "key": ""}, "reason": "not_found"}
    ]


# ── 不属于项目的单元（全局资产库、工作区记忆等） ─────────────────────


class InMemoryGlobalUnit:
    """不属于任何项目的单元替身：内容存在字典里，可以从别处直接改。"""

    kind = "note"
    scope = "global"

    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {"k": {"body": "初稿"}}

    async def read(self, key: str) -> dict[str, Any]:
        if key not in self.store:
            from server.services.collab.units import UnitNotFoundError

            raise UnitNotFoundError(key)
        return dict(self.store[key])

    async def write(self, key: str, changes: dict[str, Any]) -> None:
        self.store[key].update(changes)


GLOBAL_REF = UnitRef(project="", kind="note", key="k")


@pytest.fixture
async def global_hub(hub_project_files, changes):
    unit = InMemoryGlobalUnit()
    instance = CollabHub(
        hub_project_files,
        {**UNIT_SPECS, "note": unit},
        changes,
        error_text=lambda code, _detail, locale, _params: f"[{locale}] {code}",
        debounce=0.05,
        max_wait=0.2,
        close_grace=0.05,
        poll_interval=0.05,
    )
    yield instance, unit
    await instance.shutdown()


async def test_a_global_unit_is_written_back_without_a_project(global_hub) -> None:
    hub, unit = global_hub
    alice = FakeConn("c1", "alice")
    await hub.join(alice, GLOBAL_REF)
    await hub.on_sync(alice, GLOBAL_REF, create_sync_message(alice.doc))

    await hub.on_sync(alice, GLOBAL_REF, alice.type_into("body", 0, "新"))
    await alice.written_back()

    assert unit.store["k"]["body"] == "新初稿"


async def test_a_global_unit_picks_up_changes_made_elsewhere(global_hub) -> None:
    hub, unit = global_hub
    alice = FakeConn("c1", "alice")
    await hub.join(alice, GLOBAL_REF)
    await hub.on_sync(alice, GLOBAL_REF, create_sync_message(alice.doc))

    # 别人经接口改了内容，没有任何项目事件
    unit.store["k"]["body"] = "别处改的"

    # 打开期间的定时重读把它并进文档
    await alice.until(lambda: alice.text("body") != "初稿")
    assert alice.text("body") == "别处改的"
