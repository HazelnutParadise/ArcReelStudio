"""系列的路由：建立与改名、共用设定、项目归属（一个项目至多一个系列）、系列资产，以及 Agent 读到的系列设定。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from lib.db import get_async_session
from lib.db.repositories.asset_repo import AssetRepository
from lib.project.project_manager import ProjectManager
from server.agent_runtime.agent_access_policy import AgentAccessPolicy
from server.agent_runtime.options_assembler import OptionsAssembler
from server.auth import CurrentUserInfo, get_current_user
from server.error_handlers import register_error_handlers
from server.routers import series
from tests.auth_deps import AUTH_DEPENDENCIES
from tests.fakes import use_project_manager

BASE = "/api/v1/series"


@pytest.fixture
def series_projects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ProjectManager:
    manager = ProjectManager(str(tmp_path / "projects"))
    for name in ("s1", "s2"):
        manager.create_project(name)
        manager.create_project_metadata(name, name.upper(), "Anime", "narration")
    use_project_manager(monkeypatch, manager)
    return manager


@pytest.fixture
async def series_client(db_factory, series_projects):
    app = FastAPI()
    register_error_handlers(app)

    async def override_session():
        async with db_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_async_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="u-bob", sub="bob", role="user")
    app.include_router(series.router, prefix="/api/v1", dependencies=AUTH_DEPENDENCIES)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client


async def _asset(db_factory, name: str) -> str:
    async with db_factory() as session:
        asset = await AssetRepository(session).create(type="character", name=name, description="主角")
        await session.commit()
        return asset.id


async def _create(client: AsyncClient, name: str) -> dict:
    response = await client.post(BASE, json={"name": name, "description": "同一个世界的几部剧"})
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_series_is_created_listed_and_its_settings_updated(series_client) -> None:
    created = await _create(series_client, "  长安夜  ")
    updated = await series_client.patch(
        f"{BASE}/{created['id']}", json={"world_setting": "唐代长安，宵禁森严", "plot_setting": "每部剧一桩夜案"}
    )
    listed = (await series_client.get(BASE)).json()["series"]

    assert created["name"] == "长安夜"
    assert (created["project_names"], created["asset_ids"]) == ([], [])
    assert updated.json()["world_setting"] == "唐代长安，宵禁森严"
    assert updated.json()["description"] == "同一个世界的几部剧"
    assert [(entry["name"], entry["plot_setting"]) for entry in listed] == [("长安夜", "每部剧一桩夜案")]


async def test_series_names_are_unique(series_client) -> None:
    first = await _create(series_client, "长安夜")
    second = await _create(series_client, "洛阳春")

    duplicate = await series_client.post(BASE, json={"name": "长安夜"})
    renamed_onto_other = await series_client.patch(f"{BASE}/{second['id']}", json={"name": "长安夜"})
    renamed_to_itself = await series_client.patch(f"{BASE}/{first['id']}", json={"name": "长安夜"})
    blank = await series_client.post(BASE, json={"name": "   "})

    assert (duplicate.status_code, renamed_onto_other.status_code) == (409, 409)
    assert renamed_to_itself.status_code == 200
    assert blank.status_code == 422


async def test_a_project_belongs_to_at_most_one_series(series_client) -> None:
    first = await _create(series_client, "长安夜")
    second = await _create(series_client, "洛阳春")

    await series_client.put(f"{BASE}/{first['id']}/projects/s1")
    moved = await series_client.put(f"{BASE}/{second['id']}/projects/s1")
    unknown = await series_client.put(f"{BASE}/{first['id']}/projects/nope")
    by_id = {entry["id"]: entry for entry in (await series_client.get(BASE)).json()["series"]}

    assert moved.json()["project_names"] == ["s1"]
    assert unknown.status_code == 404
    assert (by_id[first["id"]]["project_names"], by_id[second["id"]]["project_names"]) == ([], ["s1"])


async def test_removing_a_project_and_deleting_a_series_leave_the_projects_alone(
    series_client, series_projects
) -> None:
    created = await _create(series_client, "长安夜")
    await series_client.put(f"{BASE}/{created['id']}/projects/s1")
    await series_client.put(f"{BASE}/{created['id']}/projects/s2")

    removed = await series_client.delete(f"{BASE}/{created['id']}/projects/s1")
    deleted = await series_client.delete(f"{BASE}/{created['id']}")
    missing = await series_client.get(f"{BASE}/{created['id']}")

    assert removed.json()["project_names"] == ["s2"]
    assert (deleted.status_code, missing.status_code) == (204, 404)
    assert sorted(series_projects.list_projects()) == ["s1", "s2"]


async def test_a_deleted_project_no_longer_shows_in_its_series(series_client, series_projects) -> None:
    created = await _create(series_client, "长安夜")
    await series_client.put(f"{BASE}/{created['id']}/projects/s1")

    series_projects.delete_project_directory("s1")
    shown = (await series_client.get(f"{BASE}/{created['id']}")).json()

    assert shown["project_names"] == []


async def test_series_assets_are_library_entries_added_once(series_client, db_factory) -> None:
    created = await _create(series_client, "长安夜")
    hero = await _asset(db_factory, "李慕白")
    sidekick = await _asset(db_factory, "阿七")

    await series_client.put(f"{BASE}/{created['id']}/assets/{hero}")
    await series_client.put(f"{BASE}/{created['id']}/assets/{hero}")
    added = await series_client.put(f"{BASE}/{created['id']}/assets/{sidekick}")
    unknown = await series_client.put(f"{BASE}/{created['id']}/assets/not-an-asset")
    removed = await series_client.delete(f"{BASE}/{created['id']}/assets/{hero}")

    assert added.json()["asset_ids"] == [hero, sidekick]
    assert unknown.status_code == 404
    assert removed.json()["asset_ids"] == [sidekick]


async def test_an_asset_deleted_from_the_library_drops_out_of_the_series(series_client, db_factory) -> None:
    created = await _create(series_client, "长安夜")
    hero = await _asset(db_factory, "李慕白")
    await series_client.put(f"{BASE}/{created['id']}/assets/{hero}")

    async with db_factory() as session:
        await AssetRepository(session).delete(hero)
        await session.commit()
    shown = (await series_client.get(f"{BASE}/{created['id']}")).json()

    assert shown["asset_ids"] == []


def _assembler(tmp_path: Path, db_factory) -> OptionsAssembler:
    data_root = (tmp_path / "projects").resolve()
    policy = AgentAccessPolicy(
        project_root=(tmp_path / "repo").resolve(),
        data_root=data_root,
        agent_profile_root=(tmp_path / "profile").resolve(),
        sandbox_enabled=False,
        in_docker=False,
    )
    return OptionsAssembler(
        data_root=data_root,
        allowed_tools=["Read"],
        setting_sources=["project"],
        access_policy_provider=lambda: policy,
        max_turns_provider=lambda: None,
        resolve_project_cwd=lambda name: data_root / name,
        session_factory_provider=lambda: db_factory,
    )


async def test_the_agent_reads_the_series_setting_of_its_project(series_client, db_factory, tmp_path: Path) -> None:
    created = await _create(series_client, "长安夜")
    await series_client.patch(
        f"{BASE}/{created['id']}", json={"world_setting": "唐代长安，宵禁森严", "plot_setting": "每部剧一桩夜案"}
    )
    await series_client.put(f"{BASE}/{created['id']}/projects/s1")
    assembler = _assembler(tmp_path, db_factory)

    in_series = await assembler._build_append_prompt("s1")
    outside = await assembler._build_append_prompt("s2")

    assert "系列「长安夜」" in in_series
    assert "唐代长安，宵禁森严" in in_series
    assert "每部剧一桩夜案" in in_series
    assert "所属系列的共用设定" not in outside


async def test_a_series_without_settings_adds_nothing_to_the_agent_prompt(series_client, db_factory, tmp_path) -> None:
    created = await _create(series_client, "长安夜")
    await series_client.put(f"{BASE}/{created['id']}/projects/s1")

    prompt = await _assembler(tmp_path, db_factory)._build_append_prompt("s1")

    assert "所属系列的共用设定" not in prompt
