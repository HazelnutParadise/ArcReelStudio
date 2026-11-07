"""多人协作的事件流：变更批次带上发起写入的成员，在线成员的增减经同一事件流广播。

前端据 ``actor`` 区分自己与其他成员的 Web 端修改：其他成员的修改照常提示，但不自动跳转。
扫描批次的成员按读盘前送达的 hint 结算；同一窗口里有多位成员的写入时无法归属，``actor`` 为空。
"""

from __future__ import annotations

import asyncio

import pytest

from lib.project.project_change_hints import (
    emit_project_change_batch,
    emit_project_change_hint,
    project_change_actor,
    project_change_source,
)
from lib.project.project_manager import ProjectManager
from server.services.project.project_events import PRESENCE_EVENT, ProjectEventService
from server.services.project.project_presence import ProjectPresenceService

ALICE = {"user_id": "u-alice", "username": "alice"}
BOB = {"user_id": "u-bob", "username": "bob"}
# 定时轮询不参与：扫描只由 hint 唤醒。
_POLL_SECONDS = 3600.0


async def _next_event(stream, *, timeout: float) -> tuple[str, dict]:  # noqa: ASYNC109 -- 测试轮询 helper 的等待上限，非生产取消语义
    async def _pull() -> tuple[str, dict]:
        async for item in stream:
            if isinstance(item, dict):
                if item.get("type") == "_idle":
                    continue
                raise AssertionError(f"unexpected dict sentinel: {item}")
            return item
        raise AssertionError("stream ended before a real event arrived")

    return await asyncio.wait_for(_pull(), timeout=timeout)


def _segment_change() -> dict:
    return {
        "entity_type": "segment",
        "action": "updated",
        "entity_id": "E1S01",
        "label": "分镜「E1S01」",
        "focus": None,
        "important": True,
    }


def _demo_project(tmp_path) -> ProjectManager:
    pm = ProjectManager(tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", "Demo", "Anime", "narration")
    return pm


def _rename_project(pm: ProjectManager, title: str) -> None:
    project = pm.load_project("demo")
    project["title"] = title
    pm.save_project("demo", project)


@pytest.fixture
async def event_service(tmp_path):
    _demo_project(tmp_path)
    svc = ProjectEventService(tmp_path, poll_interval=_POLL_SECONDS)
    await svc.start()
    try:
        yield svc
    finally:
        await svc.shutdown()


async def test_an_emitted_batch_names_the_member_who_made_the_edit(event_service):
    async with event_service.stream_events("demo", idle_timeout=0.1) as stream:
        assert (await anext(stream))[0] == "snapshot"

        with project_change_actor(ALICE):
            emit_project_change_batch("demo", [_segment_change()], source="webui")

        event_name, payload = await _next_event(stream, timeout=1.0)
        assert event_name == "changes"
        assert payload["source"] == "webui"
        assert payload["actor"] == ALICE


async def test_batches_from_workers_carry_no_member(event_service):
    async with event_service.stream_events("demo", idle_timeout=0.1) as stream:
        assert (await anext(stream))[0] == "snapshot"

        emit_project_change_batch("demo", [_segment_change()], source="worker")

        _event_name, payload = await _next_event(stream, timeout=1.0)
        assert payload["actor"] is None


async def test_a_scan_woken_by_a_members_write_names_that_member(event_service, tmp_path):
    pm = ProjectManager(tmp_path / "projects")
    async with event_service.stream_events("demo", idle_timeout=0.1) as stream:
        assert (await anext(stream))[0] == "snapshot"

        _rename_project(pm, "Renamed by Alice")
        with project_change_source("webui"), project_change_actor(ALICE):
            emit_project_change_hint("demo")

        event_name, payload = await _next_event(stream, timeout=2.0)
        assert event_name == "changes"
        assert payload["source"] == "webui"
        assert payload["actor"] == ALICE


async def test_a_scan_covering_writes_from_two_members_names_nobody(event_service, tmp_path):
    pm = ProjectManager(tmp_path / "projects")
    async with event_service.stream_events("demo", idle_timeout=0.1) as stream:
        assert (await anext(stream))[0] == "snapshot"

        _rename_project(pm, "Renamed twice")
        # 两条 hint 都在本测试协程让出事件循环之前送出，落进同一轮扫描。
        with project_change_source("webui"), project_change_actor(ALICE):
            emit_project_change_hint("demo")
        with project_change_source("webui"), project_change_actor(BOB):
            emit_project_change_hint("demo")

        _event_name, payload = await _next_event(stream, timeout=2.0)
        assert payload["source"] == "webui"
        assert payload["actor"] is None


async def test_presence_changes_are_broadcast_to_project_subscribers(event_service):
    presence = ProjectPresenceService(publish=event_service.publish_presence)
    async with event_service.stream_events("demo", idle_timeout=0.1) as stream:
        assert (await anext(stream))[0] == "snapshot"

        presence.heartbeat("demo", "tab-1", user_id="u-alice", username="alice", view="episodes/1")

        event_name, payload = await _next_event(stream, timeout=1.0)
        assert event_name == PRESENCE_EVENT
        assert payload == {
            "project_name": "demo",
            "members": [{"user_id": "u-alice", "username": "alice", "views": ["episodes/1"]}],
        }
