"""在线成员登记：按成员汇总各标签页正在看的位置，名单变化时才广播，过期的标签页由清扫移除。"""

from __future__ import annotations

import pytest

from server.services.project.project_presence import MAX_TABS_PER_MEMBER, PRESENCE_TTL_SECONDS, ProjectPresenceService


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def published() -> list[tuple[str, dict]]:
    return []


@pytest.fixture
def presence(clock, published) -> ProjectPresenceService:
    return ProjectPresenceService(publish=lambda project, payload: published.append((project, payload)), clock=clock)


def _alice(presence: ProjectPresenceService, tab: str = "tab-1", view: str | None = "episodes/1") -> list[dict]:
    return presence.heartbeat("demo", tab, user_id="u-alice", username="alice", view=view)


def test_a_heartbeat_lists_the_member_and_broadcasts_the_new_roster(presence, published):
    members = _alice(presence)

    assert members == [{"user_id": "u-alice", "username": "alice", "views": ["episodes/1"]}]
    assert published == [("demo", {"project_name": "demo", "members": members})]


def test_a_member_with_several_tabs_is_listed_once_with_every_view(presence):
    _alice(presence, "tab-1", "episodes/1")
    members = _alice(presence, "tab-2", "assets")

    assert members == [{"user_id": "u-alice", "username": "alice", "views": ["assets", "episodes/1"]}]


def test_members_are_sorted_by_username_and_tabs_without_a_view_add_none(presence):
    presence.heartbeat("demo", "tab-b", user_id="u-bob", username="bob", view=None)
    members = _alice(presence)

    assert [m["username"] for m in members] == ["alice", "bob"]
    assert members[1]["views"] == []


def test_heartbeats_that_do_not_change_the_roster_are_not_broadcast(presence, published):
    _alice(presence)
    _alice(presence)

    assert len(published) == 1


def test_projects_keep_separate_rosters(presence, published):
    _alice(presence)
    presence.heartbeat("other", "tab-9", user_id="u-bob", username="bob", view=None)

    assert presence.members("demo") == [{"user_id": "u-alice", "username": "alice", "views": ["episodes/1"]}]
    assert [project for project, _ in published] == ["demo", "other"]


def test_leaving_removes_the_tab_and_broadcasts(presence, published):
    _alice(presence)

    presence.leave("demo", "tab-1")

    assert presence.members("demo") == []
    assert published[-1] == ("demo", {"project_name": "demo", "members": []})


def test_leaving_an_unknown_tab_broadcasts_nothing(presence, published):
    presence.leave("demo", "missing")

    assert published == []


def test_sweeping_drops_tabs_that_stopped_sending_heartbeats(presence, published, clock):
    _alice(presence, "tab-1")
    clock.now += PRESENCE_TTL_SECONDS - 1
    _alice(presence, "tab-2", "assets")
    clock.now += 2

    presence.sweep()

    assert presence.members("demo") == [{"user_id": "u-alice", "username": "alice", "views": ["assets"]}]
    assert published[-1][1]["members"] == presence.members("demo")


def test_sweeping_without_expired_tabs_broadcasts_nothing(presence, published):
    _alice(presence)

    presence.sweep()

    assert len(published) == 1


def test_a_failing_publisher_does_not_break_heartbeats(clock):
    def boom(_project: str, _payload: dict) -> None:
        raise RuntimeError("subscriber gone")

    presence = ProjectPresenceService(publish=boom, clock=clock)

    assert presence.heartbeat("demo", "tab-1", user_id="u-alice", username="alice", view=None)[0]["username"] == "alice"


def test_each_member_keeps_only_their_most_recent_tabs(presence, clock):
    for index in range(MAX_TABS_PER_MEMBER + 3):
        clock.now += 1
        _alice(presence, f"tab-{index}", f"episodes/{index}")

    views = presence.members("demo")[0]["views"]
    assert len(views) == MAX_TABS_PER_MEMBER
    assert "episodes/0" not in views
