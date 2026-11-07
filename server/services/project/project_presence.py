"""项目在线成员：各标签页定时报到正在看的位置，名单变化时经项目事件流广播。

登记只在进程内存里，重启后由各标签页的下一次报到重建；名单按成员汇总，同一成员开了几个标签页只列一次。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: 超过这么久没有报到的标签页视为已离开。前端每 20 秒报到一次，留出两次以上的余量。
PRESENCE_TTL_SECONDS = 45.0
#: 清扫过期标签页的间隔。
PRESENCE_SWEEP_SECONDS = 15.0
#: 每位成员在一个项目里最多保留的标签页数；超出时丢弃最久没有报到的，避免伪造的标签页标识撑大登记表。
MAX_TABS_PER_MEMBER = 20

#: 广播在线名单：``(项目名, {"project_name", "members"})``。
PresencePublisher = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class _Tab:
    user_id: str
    username: str
    view: str | None
    seen_at: float


class ProjectPresenceService:
    """在线成员登记。所有方法须在事件循环线程调用。"""

    def __init__(
        self,
        publish: PresencePublisher,
        *,
        ttl_seconds: float = PRESENCE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._publish = publish
        self._ttl = ttl_seconds
        self._clock = clock
        self._tabs: dict[str, dict[str, _Tab]] = {}
        self._sweeper: asyncio.Task[None] | None = None

    def heartbeat(
        self, project_name: str, client_id: str, *, user_id: str, username: str, view: str | None
    ) -> list[dict[str, Any]]:
        """登记一个标签页正在看的位置，返回项目当前的在线名单；名单有变化时广播。"""
        tabs = self._tabs.setdefault(project_name, {})
        before = _roster(tabs)
        tabs[client_id] = _Tab(user_id=user_id, username=username, view=view, seen_at=self._clock())
        own = sorted((tab.seen_at, cid) for cid, tab in tabs.items() if tab.user_id == user_id)
        for _seen_at, stale in own[:-MAX_TABS_PER_MEMBER]:
            del tabs[stale]
        after = _roster(tabs)
        if after != before:
            self._broadcast(project_name, after)
        return after

    def leave(self, project_name: str, client_id: str, *, user_id: str | None = None) -> None:
        """标签页关闭时离开；未登记的标签页，或给了 ``user_id`` 而标签页不属于这位成员时，不做任何事。"""
        tabs = self._tabs.get(project_name)
        if not tabs or client_id not in tabs:
            return
        if user_id is not None and tabs[client_id].user_id != user_id:
            return
        before = _roster(tabs)
        del tabs[client_id]
        self._settle(project_name, tabs, before)

    def members(self, project_name: str) -> list[dict[str, Any]]:
        return _roster(self._tabs.get(project_name, {}))

    def sweep(self) -> None:
        """移除超过有效期没有报到的标签页，名单变化的项目各广播一次。"""
        cutoff = self._clock() - self._ttl
        for project_name, tabs in list(self._tabs.items()):
            expired = [client_id for client_id, tab in tabs.items() if tab.seen_at < cutoff]
            if not expired:
                continue
            before = _roster(tabs)
            for client_id in expired:
                del tabs[client_id]
            self._settle(project_name, tabs, before)

    def start(self, interval: float = PRESENCE_SWEEP_SECONDS) -> None:
        if self._sweeper is None:
            self._sweeper = asyncio.create_task(self._sweep_forever(interval), name="project-presence-sweeper")

    async def shutdown(self) -> None:
        sweeper, self._sweeper = self._sweeper, None
        if sweeper is not None:
            sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweeper

    async def _sweep_forever(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            self.sweep()

    def _settle(self, project_name: str, tabs: dict[str, _Tab], before: list[dict[str, Any]]) -> None:
        if not tabs:
            del self._tabs[project_name]
        after = _roster(tabs)
        if after != before:
            self._broadcast(project_name, after)

    def _broadcast(self, project_name: str, members: list[dict[str, Any]]) -> None:
        try:
            self._publish(project_name, {"project_name": project_name, "members": members})
        except Exception:
            logger.exception("广播在线成员失败 project=%s", project_name)


def _roster(tabs: dict[str, _Tab]) -> list[dict[str, Any]]:
    """按成员汇总的在线名单：用户名排序，每位成员的位置去重排序。"""
    views: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    for tab in tabs.values():
        names[tab.user_id] = tab.username
        member_views = views.setdefault(tab.user_id, set())
        if tab.view:
            member_views.add(tab.view)
    return [
        {"user_id": user_id, "username": names[user_id], "views": sorted(views[user_id])}
        for user_id in sorted(names, key=lambda uid: (names[uid], uid))
    ]
