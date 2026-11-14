"""跨版本恢复：升级前写下的删除记录经临时项目的迁移链恢复；迁移失败时降级为只恢复文件，结构文件只能下载。

删除记录用 schema 19 的项目样本构造，再把当前项目升级到最新 schema，模拟「删除后应用升级」。迁移链不接的
更早版本的记录同样降级。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lib.edit_timeline.store import read_timeline_document
from lib.infra.data_root_layout import DataRootLayout
from lib.project import project_trash
from lib.project.project_manager import ProjectManager
from lib.project.project_migration_failure import ProjectMigrationError
from lib.project.project_migrations.runner import migrate_project_dir
from server.error_handlers import register_error_handlers
from server.routers import project_trash as trash_router
from tests.auth_deps import override_auth
from tests.factories import wrap_the_last_migration_step
from tests.fakes import use_project_manager
from tests.legacy_project_shapes import SCHEMA_V19, write_legacy_timeline_project

TIMELINE = "tl-0000abcd"
DOCUMENT = f"edit_timelines/episode_1/{TIMELINE}.json"
RENDER = f"renders/episode_1/{TIMELINE}/final.mp4"


@pytest.fixture
def projects_dir(tmp_path: Path) -> Path:
    root = DataRootLayout(tmp_path / "data").projects_dir
    root.mkdir(parents=True)
    return root


@pytest.fixture
def cross_version_client(projects_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    manager = ProjectManager(str(projects_dir.parent))
    use_project_manager(monkeypatch, manager)
    app = FastAPI()
    app.include_router(trash_router.router, prefix="/api/v1")
    register_error_handlers(app)
    override_auth(app)
    return TestClient(app)


def _old_record(project_dir: Path, files: list[str], *, schema_version: int) -> str:
    """在旧 schema 的项目里删除一条剪辑时间线，记录标成当时的 schema 版本。"""
    obj = {"kind": "edit_timeline", "id": TIMELINE, "episode": 1, "name": "初剪"}
    record = project_trash.record_deletion(project_dir, obj, files, snapshot=True)
    # 与删除路径一样撤掉只剩空壳的渲染目录
    for rel in files:
        if rel.startswith("renders/"):
            (project_dir / rel).parent.rmdir()
    record_file = project_trash.trash_dir(project_dir) / record.id / "record.json"
    data = json.loads(record_file.read_text(encoding="utf-8"))
    record_file.write_text(json.dumps({**data, "schema_version": schema_version}), encoding="utf-8")
    return record.id


def _set_schema_version(project_dir: Path, version: int) -> None:
    project_file = project_dir / "project.json"
    project = json.loads(project_file.read_text(encoding="utf-8"))
    project_file.write_text(json.dumps({**project, "schema_version": version}, ensure_ascii=False), encoding="utf-8")


def _fail_migrating_staged_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    """临时项目的迁移链在数据上失败（不是读写故障）：当前项目已在最新 schema，不再进链。"""

    def fail(_step: object, _project_dir: Path, **_kwargs: object) -> object:
        raise ProjectMigrationError("scripts/episode_1.json is not valid UTF-8 JSON", file="scripts/episode_1.json")

    wrap_the_last_migration_step(monkeypatch, fail)


def _trash(client: TestClient, project: str) -> list[dict]:
    response = client.get(f"/api/v1/projects/{project}/trash")
    assert response.status_code == 200, response.text
    return response.json()["records"]


def _timeline_project(projects_dir: Path) -> Path:
    project_dir = write_legacy_timeline_project(projects_dir)
    (project_dir / RENDER).parent.mkdir(parents=True)
    (project_dir / RENDER).write_bytes(b"final-cut")
    return project_dir


def test_a_record_from_an_older_schema_is_migrated_and_restored(
    cross_version_client: TestClient, projects_dir: Path
) -> None:
    project_dir = _timeline_project(projects_dir)
    record_id = _old_record(project_dir, [DOCUMENT, RENDER], schema_version=SCHEMA_V19)
    migrate_project_dir(project_dir)  # 应用升级

    restored = cross_version_client.post(f"/api/v1/projects/{project_dir.name}/trash/{record_id}/restore")

    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert (body["degraded"], body["download_only"], body["object"]["id"], body["object"]["name"]) == (
        False,
        [],
        TIMELINE,
        "初剪",
    )
    assert read_timeline_document(project_dir, 1, TIMELINE) is not None
    assert (project_dir / RENDER).read_bytes() == b"final-cut"
    assert _trash(cross_version_client, project_dir.name) == []


def _assert_degraded_to_files_and_download(
    client: TestClient, project_dir: Path, record_id: str, document_bytes: bytes
) -> None:
    base = f"/api/v1/projects/{project_dir.name}/trash/{record_id}"

    restored = client.post(f"{base}/restore")

    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert body["degraded"] is True
    assert body["restored"] == [{"original": RENDER, "path": RENDER, "as_history": False}]
    assert body["download_only"] == [DOCUMENT]
    assert (project_dir / RENDER).read_bytes() == b"final-cut"
    assert not (project_dir / DOCUMENT).exists()
    [record] = _trash(client, project_dir.name)
    assert (record["id"], record["files"], record["download_only"], record["has_snapshot"]) == (
        record_id,
        [DOCUMENT],
        True,
        False,
    )
    assert record["size"] == len(document_bytes)

    downloaded = client.get(f"{base}/files", params={"path": DOCUMENT})
    assert downloaded.status_code == 200
    assert downloaded.content == document_bytes
    assert downloaded.headers["content-disposition"].startswith("attachment")
    assert client.get(f"{base}/files", params={"path": RENDER}).status_code == 404
    assert client.post(f"{base}/restore").status_code == 409


def test_a_record_whose_migration_fails_restores_its_files_and_keeps_structure_for_download(
    cross_version_client: TestClient, projects_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = _timeline_project(projects_dir)
    document_bytes = (project_dir / DOCUMENT).read_bytes()
    record_id = _old_record(project_dir, [DOCUMENT, RENDER], schema_version=SCHEMA_V19)
    migrate_project_dir(project_dir)
    _fail_migrating_staged_projects(monkeypatch)

    _assert_degraded_to_files_and_download(cross_version_client, project_dir, record_id, document_bytes)


def test_a_record_from_a_schema_older_than_19_takes_the_degraded_path(
    cross_version_client: TestClient, projects_dir: Path
) -> None:
    """删除时项目还停在 v18：迁移链不接它，记录按迁移失败降级，结构文件只能下载。"""
    project_dir = _timeline_project(projects_dir)
    document_bytes = (project_dir / DOCUMENT).read_bytes()
    _set_schema_version(project_dir, 18)
    record_id = _old_record(project_dir, [DOCUMENT, RENDER], schema_version=18)
    _set_schema_version(project_dir, SCHEMA_V19)
    migrate_project_dir(project_dir)

    _assert_degraded_to_files_and_download(cross_version_client, project_dir, record_id, document_bytes)
