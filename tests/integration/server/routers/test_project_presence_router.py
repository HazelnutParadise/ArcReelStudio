"""在线成员接口：标签页定时报到并带上正在看的位置，关闭时离开；登记以登录的账号为准。"""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lib.project.project_manager import ProjectManager
from server.auth import CurrentUserInfo, get_current_user
from server.error_handlers import register_error_handlers
from server.routers import project_presence
from server.services.project.project_presence import ProjectPresenceService
from tests.auth_deps import AUTH_DEPENDENCIES
from tests.fakes import use_project_manager


@pytest.fixture
def published() -> list[tuple[str, dict]]:
    return []


@pytest.fixture
def presence_client(tmp_path, monkeypatch, published):
    pm = ProjectManager(tmp_path / "projects")
    pm.create_project("demo")
    pm.create_project_metadata("demo", "Demo", "Anime", "narration")
    use_project_manager(monkeypatch, pm)

    app = FastAPI()
    app.state.project_presence_service = ProjectPresenceService(
        publish=lambda project, payload: published.append((project, payload))
    )
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="u-alice", sub="alice", role="user")
    app.include_router(project_presence.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    register_error_handlers(app)
    with TestClient(app) as test_client:
        yield test_client


def test_a_heartbeat_registers_the_signed_in_member_and_returns_the_roster(presence_client, published):
    response = presence_client.put("/api/v1/projects/demo/presence", json={"client_id": "tab-1", "view": "episodes/2"})

    assert response.status_code == 200
    members = [{"user_id": "u-alice", "username": "alice", "views": ["episodes/2"]}]
    assert response.json() == {"members": members}
    assert published == [("demo", {"project_name": "demo", "members": members})]


def test_the_view_is_optional(presence_client):
    response = presence_client.put("/api/v1/projects/demo/presence", json={"client_id": "tab-1"})

    assert response.status_code == 200
    assert response.json()["members"][0]["views"] == []


def test_leaving_removes_the_tab(presence_client, published):
    presence_client.put("/api/v1/projects/demo/presence", json={"client_id": "tab-1", "view": None})

    response = presence_client.delete("/api/v1/projects/demo/presence/tab-1")

    assert response.status_code == 204
    assert published[-1] == ("demo", {"project_name": "demo", "members": []})


def test_heartbeats_for_a_missing_project_are_rejected(presence_client, published):
    response = presence_client.put("/api/v1/projects/missing/presence", json={"client_id": "tab-1"})

    assert response.status_code == 404
    assert published == []


@pytest.mark.parametrize(
    "body",
    [
        {"client_id": ""},
        {"client_id": "x" * 65},
        {"client_id": "tab 1"},
        {"client_id": "tab-1", "view": "v" * 201},
    ],
)
def test_malformed_heartbeats_are_rejected(presence_client, body, published):
    response = presence_client.put("/api/v1/projects/demo/presence", json=body)

    assert response.status_code == 422
    assert published == []


def test_members_cannot_remove_someone_elses_tab(presence_client, published):
    presence_client.put("/api/v1/projects/demo/presence", json={"client_id": "tab-1"})
    cast(FastAPI, presence_client.app).dependency_overrides[get_current_user] = lambda: CurrentUserInfo(
        id="u-bob", sub="bob", role="user"
    )

    response = presence_client.delete("/api/v1/projects/demo/presence/tab-1")

    assert response.status_code == 204
    assert len(published) == 1
