"""协作中枢：两位成员同时编辑同一单元，合并、转发、写回，以及外部改动并入正在打的字。

浏览器一侧用 pycrdt 文档模拟（与 Yjs 互通），项目文件是真的，变更推送用可控的替身。
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import threading
from collections.abc import AsyncIterator
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

    async def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        if message["type"] == "sync":
            data = base64.b64decode(message["data"])
            assert data[0] == YMessageType.SYNC
            handle_sync_message(data[1:], self.doc)

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

    @contextlib.asynccontextmanager
    async def __call__(self, project: str):
        queue: asyncio.Queue = asyncio.Queue()
        self.queues[project] = queue

        async def _iter() -> AsyncIterator[Any]:
            # 与真实的项目事件流一样，先给出一份快照
            yield ("snapshot", {})
            while True:
                yield await queue.get()

        yield _iter()

    def push(self, project: str) -> None:
        self.queues[project].put_nowait(("changes", {"source": "worker"}))


async def test_a_change_made_before_the_subscription_is_ready_is_not_missed(hub, hub_project_files) -> None:
    alice = FakeConn("c1", "alice")
    await _join(hub, alice)
    # 房间已经读了内容，但订阅还没生效时就有人改了文件
    hub_project_files.update_project(PROJECT, lambda data: data["overview"].update({"genre": "科幻"}))
    await _settle()

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


async def _settle(seconds: float = 0.3) -> None:
    await asyncio.sleep(seconds)


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

    assert bob.text("synopsis") == "雨夜，街口"
    await _settle()
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
    await _settle()

    assert alice.text("synopsis") == bob.text("synopsis") == "深夜，雨夜的街口"
    assert hub_project_files.load_project(PROJECT)["overview"]["synopsis"] == "深夜，雨夜的街口"


async def test_external_change_merges_with_unsaved_typing(hub, hub_project_files, changes) -> None:
    alice = FakeConn("c1", "alice")
    await _join(hub, alice)
    await _settle(0.05)

    # Alice 在开头打了字、还没写回；同时 Agent 改了文件，在结尾加了字
    await hub.on_sync(alice, REF, alice.type_into("synopsis", 0, "深夜，"))
    hub_project_files.update_project(PROJECT, lambda data: data["overview"].update({"synopsis": "雨夜。"}))
    changes.push(PROJECT)
    await _settle()

    assert alice.text("synopsis") == "深夜，雨夜。"
    assert hub_project_files.load_project(PROJECT)["overview"]["synopsis"] == "深夜，雨夜。"


async def test_external_change_to_another_field_does_not_touch_the_typed_one(hub, hub_project_files, changes) -> None:
    alice = FakeConn("c1", "alice")
    await _join(hub, alice)
    await _settle(0.05)

    hub_project_files.update_project(PROJECT, lambda data: data["overview"].update({"genre": "爱情"}))
    changes.push(PROJECT)
    await _settle()

    assert alice.text("genre") == "爱情"
    assert alice.text("synopsis") == "雨夜"


async def test_written_back_text_is_trimmed_but_the_typist_keeps_the_space(hub, hub_project_files) -> None:
    alice = FakeConn("c1", "alice")
    await _join(hub, alice)

    await hub.on_sync(alice, REF, alice.type_into("synopsis", len("雨夜".encode()), " "))
    await _settle()

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
    await _settle()

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
    await _settle(0.15)

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
    await _settle()

    assert unit.store["k"]["body"] == "新初稿"


async def test_a_global_unit_picks_up_changes_made_elsewhere(global_hub) -> None:
    hub, unit = global_hub
    alice = FakeConn("c1", "alice")
    await hub.join(alice, GLOBAL_REF)
    await hub.on_sync(alice, GLOBAL_REF, create_sync_message(alice.doc))

    # 别人经接口改了内容，没有任何项目事件
    unit.store["k"]["body"] = "别处改的"
    await _settle()

    assert alice.text("body") == "别处改的"


# ── 写回与同一时刻的外部改动 ─────────────────────────────────────
#
# 外部改动已经落到存储、中枢还没重读（事件没到、轮询没轮到）时就写回：用不推送事件的变更流、很长的防抖与
# 轮询间隔，让重读只在测试点名时发生，写回只经 ``flush`` 触发。


class SilentChanges:
    """订阅一直不出任何事件的变更流：中枢不会自己重读。"""

    @contextlib.asynccontextmanager
    async def __call__(self, project: str):
        async def _iter() -> AsyncIterator[Any]:
            await asyncio.Event().wait()
            yield ("changes", {})

        yield _iter()


def _quiet_hub(pm: ProjectManager, specs: dict[str, Any]) -> CollabHub:
    return CollabHub(
        pm,
        specs,
        SilentChanges(),
        error_text=lambda code, _detail, locale, _params: f"[{locale}] {code}",
        debounce=3600,
        max_wait=3600,
        close_grace=3600,
        poll_interval=3600,
    )


@pytest.fixture
async def quiet_hub(hub_project_files):
    instance = _quiet_hub(hub_project_files, UNIT_SPECS)
    yield instance
    await instance.shutdown()


async def test_an_outside_change_to_the_typed_field_is_merged_not_overwritten(quiet_hub, hub_project_files) -> None:
    alice, bob = FakeConn("c1", "alice"), FakeConn("c2", "bob")
    await _join(quiet_hub, alice)
    await _join(quiet_hub, bob)

    # Alice 在开头打了字；写回之前 Agent 在结尾加了字，中枢还没重读
    await quiet_hub.on_sync(alice, REF, alice.type_into("synopsis", 0, "深夜，"))
    hub_project_files.update_project(PROJECT, lambda data: data["overview"].update({"synopsis": "雨夜。"}))
    await quiet_hub.flush(alice, REF, 1)

    assert hub_project_files.load_project(PROJECT)["overview"]["synopsis"] == "深夜，雨夜。"
    assert alice.text("synopsis") == bob.text("synopsis") == "深夜，雨夜。"
    assert alice.messages[-1]["ok"] is True
    assert [s["state"] for s in bob.statuses()][-2:] == ["saving", "saved"]


async def test_an_outside_change_to_another_field_reaches_every_member(quiet_hub, hub_project_files) -> None:
    alice, bob = FakeConn("c1", "alice"), FakeConn("c2", "bob")
    await _join(quiet_hub, alice)
    await _join(quiet_hub, bob)

    await quiet_hub.on_sync(alice, REF, alice.type_into("synopsis", 0, "深夜，"))
    hub_project_files.update_project(PROJECT, lambda data: data["overview"].update({"genre": "爱情"}))
    await quiet_hub.flush(alice, REF, 1)
    # 外部改动的事件随后到达
    await quiet_hub.refresh_project(PROJECT)

    overview = hub_project_files.load_project(PROJECT)["overview"]
    assert (overview["synopsis"], overview["genre"]) == ("深夜，雨夜", "爱情")
    for conn in (alice, bob):
        assert (conn.text("synopsis"), conn.text("genre")) == ("深夜，雨夜", "爱情")


async def test_an_outside_change_to_a_global_unit_is_merged_not_overwritten(hub_project_files) -> None:
    unit = InMemoryGlobalUnit()
    hub = _quiet_hub(hub_project_files, {**UNIT_SPECS, "note": unit})
    alice, bob = FakeConn("c1", "alice"), FakeConn("c2", "bob")
    for conn in (alice, bob):
        await hub.join(conn, GLOBAL_REF)
        await hub.on_sync(conn, GLOBAL_REF, create_sync_message(conn.doc))

    await hub.on_sync(alice, GLOBAL_REF, alice.type_into("body", 0, "新"))
    unit.store["k"]["body"] = "初稿。"
    await hub.flush(alice, GLOBAL_REF, 1)

    assert unit.store["k"]["body"] == "新初稿。"
    assert alice.text("body") == bob.text("body") == "新初稿。"
    await hub.shutdown()


class EverChangingGlobalUnit(InMemoryGlobalUnit):
    """每次被读都先被别处改一次：写回前的核对永远对不上。"""

    def __init__(self) -> None:
        super().__init__()
        self.armed = False
        self.writes = 0

    async def read(self, key: str) -> dict[str, Any]:
        if self.armed:
            self.store[key]["body"] += "。"
        return await super().read(key)

    async def write(self, key: str, changes: dict[str, Any]) -> None:
        self.writes += 1
        await super().write(key, changes)


async def test_an_outside_writer_that_never_stops_ends_in_an_error_instead_of_looping(hub_project_files) -> None:
    unit = EverChangingGlobalUnit()
    hub = _quiet_hub(hub_project_files, {**UNIT_SPECS, "note": unit})
    alice = FakeConn("c1", "alice")
    await hub.join(alice, GLOBAL_REF)
    await hub.on_sync(alice, GLOBAL_REF, create_sync_message(alice.doc))

    await hub.on_sync(alice, GLOBAL_REF, alice.type_into("body", 0, "新"))
    unit.armed = True
    await hub.flush(alice, GLOBAL_REF, 1)
    unit.armed = False

    assert unit.writes == 0
    assert alice.messages[-1]["ok"] is False
    assert alice.statuses()[-1]["state"] == "error"
    # 别处的改动已并进文档，Alice 打的字也还在
    assert alice.text("body").startswith("新初稿。")
    await hub.shutdown()


async def test_a_write_back_cancelled_midway_is_not_merged_in_again(quiet_hub, hub_project_files, monkeypatch) -> None:
    alice = FakeConn("c1", "alice")
    await _join(quiet_hub, alice)
    spec = UNIT_SPECS["overview"]
    original = spec.write
    loop = asyncio.get_running_loop()
    entered, release = asyncio.Event(), threading.Event()

    def _held_write(*args: Any, **kwargs: Any) -> None:
        loop.call_soon_threadsafe(entered.set)
        release.wait()
        original(*args, **kwargs)

    monkeypatch.setattr(spec, "write", _held_write)
    await quiet_hub.on_sync(alice, REF, alice.type_into("synopsis", 0, "深夜，"))
    # 写回进行到一半时被取消（房间关闭、有人重新加入都会这样），文件照样写完
    pending = asyncio.create_task(quiet_hub.flush(alice, REF, 1))
    await entered.wait()
    pending.cancel()
    release.set()
    with contextlib.suppress(asyncio.CancelledError):
        await pending
    await quiet_hub.flush(alice, REF, 2)

    assert hub_project_files.load_project(PROJECT)["overview"]["synopsis"] == "深夜，雨夜"
    assert alice.text("synopsis") == "深夜，雨夜"
