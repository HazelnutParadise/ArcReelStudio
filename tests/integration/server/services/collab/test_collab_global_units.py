"""不属于单个项目的协作单元：全局资产库条目与工作区记忆文件；以及项目记忆文件。"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.agent.agent_memory_store import AgentMemoryStore
from lib.db.repositories.asset_repo import AssetRepository
from lib.project.project_manager import ProjectManager
from server.services.collab.units import (
    LibraryAssetUnit,
    ProjectMemoryFileUnit,
    UnitNotFoundError,
    UnitWriteError,
    WorkspaceMemoryFileUnit,
)


@pytest.fixture
async def library(db_factory):
    async with db_factory() as session:
        repo = AssetRepository(session)
        alice = await repo.create(type="character", name="Alice", description="高个子", voice_style="低沉")
        await repo.create(type="character", name="Bob")
        await session.commit()
    return LibraryAssetUnit(db_factory), alice.id


async def test_library_asset_reads_its_text_fields(library) -> None:
    unit, asset_id = library
    assert await unit.read(asset_id) == {"name": "Alice", "description": "高个子", "voice_style": "低沉"}


async def test_library_asset_writes_with_the_same_rules_as_the_api(library) -> None:
    unit, asset_id = library

    await unit.write(asset_id, {"description": "戴眼镜"})

    assert (await unit.read(asset_id))["description"] == "戴眼镜"


async def test_library_asset_rejects_a_name_another_entry_already_uses(library) -> None:
    unit, asset_id = library

    with pytest.raises(UnitWriteError) as exc:
        await unit.write(asset_id, {"name": "Bob"})

    assert exc.value.code == "asset_already_exists"
    assert (await unit.read(asset_id))["name"] == "Alice"


async def test_a_deleted_library_asset_is_reported_as_missing(library) -> None:
    unit, _ = library
    with pytest.raises(UnitNotFoundError):
        await unit.read("no-such-asset")


@pytest.fixture
def memory_projects(tmp_path: Path) -> ProjectManager:
    pm = ProjectManager(str(tmp_path / "projects"))
    pm.create_project("demo")
    return pm


def test_project_memory_file_reads_and_writes_the_file_text(memory_projects) -> None:
    unit = ProjectMemoryFileUnit()
    store = AgentMemoryStore.for_project(memory_projects.get_project_path("demo"))
    store.write("notes.md", "第一版".encode())

    assert unit.read(memory_projects, "demo", "notes.md") == {"content": "第一版"}
    unit.write(memory_projects, "demo", "notes.md", {"content": "第二版"})

    assert store.read("notes.md").decode() == "第二版"


def test_a_missing_project_memory_file_is_reported_as_missing(memory_projects) -> None:
    with pytest.raises(UnitNotFoundError):
        ProjectMemoryFileUnit().read(memory_projects, "demo", "absent.md")


async def test_workspace_memory_file_round_trips(tmp_path: Path) -> None:
    unit = WorkspaceMemoryFileUnit(lambda: AgentMemoryStore(tmp_path / "memory"))
    AgentMemoryStore(tmp_path / "memory").write("style.md", b"old")

    await unit.write("style.md", {"content": "new"})

    assert await unit.read("style.md") == {"content": "new"}


async def test_workspace_memory_rejects_an_invalid_filename(tmp_path: Path) -> None:
    unit = WorkspaceMemoryFileUnit(lambda: AgentMemoryStore(tmp_path / "memory"))
    with pytest.raises(UnitNotFoundError):
        await unit.read("../escape.md")
