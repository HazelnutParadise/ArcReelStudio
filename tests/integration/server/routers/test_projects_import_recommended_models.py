"""导入 v19 的项目归档：只写了内置供应商的模型字段改写为目录的推荐模型，跳过用户停用的推荐（docs/adr/0130）。

其余入口（启动迁移、回收站与已删除项目的恢复、迁移重试）直接用目录的推荐，见
``tests/integration/lib/project/project_migrations/test_project_migration_v19_v20.py``。
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from lib.db.models.builtin_provider_model import BuiltinProviderModelState
from lib.project.project_manager import ProjectManager
from lib.project.project_schema import CURRENT_PROJECT_SCHEMA_VERSION
from server.services.project import project_archive as project_archive_module
from server.services.project.project_archive import ProjectArchiveService
from tests.catalog_support import (
    ARK_VIDEO,
    DASHSCOPE_TTS,
    GROK_TEXT,
    OPENAI_IMAGE,
)
from tests.integration.server.routers.projects_router_support import build_projects_client
from tests.legacy_project_shapes import write_legacy_bare_provider_project

pytestmark = pytest.mark.usefixtures("recommended_models")


def _v19_archive(tmp_path: Path) -> bytes:
    """schema 19 项目的归档：模拟上一版发行版的导出器（它把 19 当作当前版本）。"""
    source = ProjectManager(tmp_path / "source")
    project_dir = write_legacy_bare_provider_project(source.projects_dir)
    with pytest.MonkeyPatch.context() as exporter:
        exporter.setattr(project_archive_module, "project_schema_is_current", lambda _project: True)
        archive_path, _ = ProjectArchiveService(source).export_project(project_dir.name)
    return archive_path.read_bytes()


def _with_schema_version(archive: bytes, version: int) -> bytes:
    """把归档里项目的 ``schema_version`` 改成 ``version``（其余内容不动）。"""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(archive)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for member in source.infolist():
            data = source.read(member)
            if member.filename.endswith("/project.json"):
                project = json.loads(data)
                project["schema_version"] = version
                data = json.dumps(project, ensure_ascii=False).encode("utf-8")
            target.writestr(member, data)
    return out.getvalue()


def _import(client, archive: bytes) -> dict[str, Any]:
    response = client.post(
        "/api/v1/projects/import",
        files={"file": ("legacy.zip", archive, "application/zip")},
        # 升级报告要用户确认一次；这里只关心导入后的模型字段
        data={"conflict_policy": "rename", "confirm_report": "true"},
    )
    assert response.status_code == 200, response.text
    return response.json()["project"]


async def _disable(db_factory, *models: tuple[str, str]) -> None:
    async with db_factory() as session:
        for provider_id, model_id in models:
            session.add(BuiltinProviderModelState(provider_id=provider_id, model_id=model_id, enabled=False))
        await session.commit()


async def test_importing_a_v19_archive_rewrites_bare_providers_to_the_recommendations(
    tmp_path, monkeypatch, db_factory
):
    archive = _v19_archive(tmp_path)
    target = ProjectManager(tmp_path / "target")

    with build_projects_client(monkeypatch, target, session_factory=db_factory) as client:
        project = _import(client, archive)

    assert project["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION == 20
    assert project["video_backend"] == f"ark/{ARK_VIDEO}"
    assert project["image_provider_t2i"] == f"openai/{OPENAI_IMAGE}"
    assert project["text_backend_complex"] == f"grok/{GROK_TEXT}"
    assert project["audio_backend"] == f"dashscope/{DASHSCOPE_TTS}"
    # 没有推荐的、自定义供应商的、完整值、音乐与音效、连线旁键原样保留
    assert (project["video_provider_r2v"], project["text_backend_simple"], project["default_image_backend"]) == (
        "openai",
        "custom-3",
        "openai/gpt-image-2",
    )
    assert (project["music_backend"], project["sfx_backend"]) == ("stability", "elevenlabs")
    assert project["default_text_backend_credential_id"] == 4


async def test_import_skips_a_recommendation_the_user_disabled_and_keeps_the_field_bare(
    tmp_path, monkeypatch, db_factory
):
    archive = _v19_archive(tmp_path)
    target = ProjectManager(tmp_path / "target")
    await _disable(db_factory, ("ark", ARK_VIDEO), ("dashscope", DASHSCOPE_TTS))

    with build_projects_client(monkeypatch, target, session_factory=db_factory) as client:
        project = _import(client, archive)

    # 停用的推荐不写进项目，字段留裸值，导入后由用户重新选
    assert project["video_backend"] == "ark"
    assert project["audio_backend"] == "dashscope"
    # 没停用的照常改写
    assert project["image_provider_t2i"] == f"openai/{OPENAI_IMAGE}"
    assert project["text_backend_complex"] == f"grok/{GROK_TEXT}"
    assert project["default_text_backend"] == f"grok/{GROK_TEXT}"


async def test_disabling_other_models_does_not_stop_the_rewrite(tmp_path, monkeypatch, db_factory):
    archive = _v19_archive(tmp_path)
    target = ProjectManager(tmp_path / "target")
    await _disable(db_factory, ("ark", "doubao-seedance-2-0-fast-260128"), ("openai", "gpt-image-2"))

    with build_projects_client(monkeypatch, target, session_factory=db_factory) as client:
        project = _import(client, archive)

    assert project["video_backend"] == f"ark/{ARK_VIDEO}"
    assert project["image_provider_t2i"] == f"openai/{OPENAI_IMAGE}"


async def test_importing_a_v20_archive_leaves_bare_values_as_they_are(tmp_path, monkeypatch, db_factory):
    archive = _with_schema_version(_v19_archive(tmp_path), CURRENT_PROJECT_SCHEMA_VERSION)
    target = ProjectManager(tmp_path / "target")

    with build_projects_client(monkeypatch, target, session_factory=db_factory) as client:
        project = _import(client, archive)

    assert project["schema_version"] == 20
    assert (project["video_backend"], project["image_provider_t2i"], project["audio_backend"]) == (
        "ark",
        "openai/",
        "dashscope",
    )
    assert project["text_backend_complex"] == " grok "
