"""v19→v20 迁移：只写了内置供应商的项目模型字段，改写为 ``provider/目录推荐模型``（docs/adr/0130）。

整条链从 v7 与 v19 走到当前版本，并断言用户看到的结果：工作台显示的视频模型、生成用的图片与文本模型、制作状态。
启动期迁移与归档导入用同一步，归档导入另外跳过用户停用的推荐，见 ``tests/integration/server/routers``。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lib.backends.text_backends.base import TextTaskType
from lib.catalog import query as catalog
from lib.catalog.errors import ModelNotSelectedError
from lib.config.resolver import ConfigResolver, ProviderModel
from lib.db.models.builtin_provider_model import BuiltinProviderModelState
from lib.infra.app_data_dir import app_data_dir
from lib.project.project_manager import ProjectManager
from lib.project.project_migrations import CURRENT_SCHEMA_VERSION, run_project_migrations
from lib.project.project_migrations.runner import migrate_project_dir
from lib.workflow.workflow_state import WorkflowStateService
from tests.catalog_support import (
    ARK_VIDEO,
    DASHSCOPE_TTS,
    GROK_TEXT,
    OPENAI_IMAGE,
    install_catalog,
    with_recommendation,
)
from tests.legacy_project_shapes import write_legacy_bare_provider_project

pytestmark = pytest.mark.usefixtures("recommended_models")


_KEPT = (
    "video_provider_r2v",
    "text_backend_simple",
    "default_image_backend",
    "music_backend",
    "sfx_backend",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _storyboard_counts(project_dir: Path) -> tuple[int, int]:
    summary = WorkflowStateService(ProjectManager(project_dir.parent.parent)).get_project_summary(project_dir.name)
    storyboards = summary.episodes[0].storyboards
    return storyboards.available, storyboards.stale


@pytest.mark.parametrize("schema_version", [7, 19])
async def test_bare_providers_become_the_recommended_models_and_stay_that_way(
    schema_version: int, session_factory
) -> None:
    """从更早的版本或上一版升级：裸供应商固化为目录此刻的推荐，之后不随目录变化；其余字段原样保留。"""
    project_dir = write_legacy_bare_provider_project(app_data_dir() / "projects", schema_version=schema_version)
    legacy = _read_json(project_dir / "project.json")

    assert migrate_project_dir(project_dir) is True

    migrated = _read_json(project_dir / "project.json")
    assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION == 20
    assert migrated["video_backend"] == f"ark/{ARK_VIDEO}"
    assert migrated["image_provider_t2i"] == f"openai/{OPENAI_IMAGE}"
    assert migrated["text_backend_complex"] == f"grok/{GROK_TEXT}"
    assert migrated["default_text_backend"] == f"grok/{GROK_TEXT}"
    assert migrated["audio_backend"] == f"dashscope/{DASHSCOPE_TTS}"
    # 没有推荐的、自定义供应商的、完整值，以及没有推荐可言的音乐与音效，原样保留
    assert {key: migrated[key] for key in _KEPT} == {key: legacy[key] for key in _KEPT}
    # 连线旁键不动：字段只补模型，供应商与连线不变
    assert migrated["default_text_backend_credential_id"] == 4
    assert [path.name for path in project_dir.glob("project.json.bak.v19-*")]

    # 用户口径：工作台显示的视频模型、生成用的图片与文本模型是迁移时的推荐，制作状态不变
    resolver = ConfigResolver(session_factory)
    caps = await resolver.video_capabilities_for_project(migrated, generation_type="i2v")
    assert (caps["provider_id"], caps["model"]) == ("ark", ARK_VIDEO)
    image = await resolver.resolve_image_backend(migrated, None, generation_type="t2i")
    assert (image.provider_id, image.model_id) == ("openai", OPENAI_IMAGE)
    assert await resolver.text_backend_for_task(TextTaskType.SCRIPT, project_dir.name) == ProviderModel(
        "grok", GROK_TEXT
    )
    assert _storyboard_counts(project_dir) == (2, 0)


async def test_a_bare_provider_without_a_recommendation_still_asks_for_a_model(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """目录没有 ark 的视频推荐：视频字段的裸值迁移后原样保留，用户看到「没有选定具体模型」并重新选择。"""
    install_catalog(monkeypatch, with_recommendation(catalog.factory_snapshot(), "ark", "video", None))
    project_dir = write_legacy_bare_provider_project(app_data_dir() / "projects", schema_version=19)

    assert migrate_project_dir(project_dir) is True

    migrated = _read_json(project_dir / "project.json")
    assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
    assert migrated["video_backend"] == "ark"
    # 其余字段照常改写
    assert migrated["text_backend_complex"] == f"grok/{GROK_TEXT}"
    with pytest.raises(ModelNotSelectedError) as error:
        await ConfigResolver(session_factory).video_capabilities_for_project(migrated, generation_type="i2v")
    assert (error.value.code, error.value.params) == ("model_not_selected", {"provider": "ark"})


def test_the_step_keeps_the_last_activity_time(tmp_path: Path) -> None:
    project_dir = write_legacy_bare_provider_project(tmp_path / "projects", schema_version=19)
    legacy = _read_json(project_dir / "project.json")

    assert migrate_project_dir(project_dir) is True

    assert _read_json(project_dir / "project.json")["metadata"] == legacy["metadata"]


def test_narration_with_only_a_music_recommendation_keeps_the_bare_provider(tmp_path: Path) -> None:
    """elevenlabs 的音频推荐是音乐模型，不能当旁白配音：留给用户重新选。"""
    project_dir = write_legacy_bare_provider_project(tmp_path / "projects", schema_version=19)
    project = _read_json(project_dir / "project.json")
    project["audio_backend"] = "elevenlabs"
    (project_dir / "project.json").write_text(json.dumps(project), encoding="utf-8")

    assert migrate_project_dir(project_dir) is True

    assert _read_json(project_dir / "project.json")["audio_backend"] == "elevenlabs"


async def test_startup_migration_uses_the_recommendation_even_when_the_user_disabled_it(
    tmp_path: Path, session_factory
) -> None:
    """启动期迁移直接用目录的推荐，不查用户的启用状态；只有归档导入跳过停用的推荐。"""
    projects_dir = tmp_path / "projects"
    project_dir = write_legacy_bare_provider_project(projects_dir, schema_version=19)
    async with session_factory() as session:
        session.add(BuiltinProviderModelState(provider_id="ark", model_id=ARK_VIDEO, enabled=False))
        await session.commit()

    summary = run_project_migrations(projects_dir)

    assert summary.migrated == [project_dir.name]
    migrated = _read_json(project_dir / "project.json")
    assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
    assert migrated["video_backend"] == f"ark/{ARK_VIDEO}"
    assert migrated["audio_backend"] == f"dashscope/{DASHSCOPE_TTS}"


def test_a_v20_project_keeps_its_bare_values_through_the_chain(tmp_path: Path) -> None:
    project_dir = write_legacy_bare_provider_project(tmp_path / "projects", schema_version=19)
    project = _read_json(project_dir / "project.json")
    project["schema_version"] = CURRENT_SCHEMA_VERSION
    (project_dir / "project.json").write_text(json.dumps(project), encoding="utf-8")
    before = (project_dir / "project.json").read_bytes()

    assert migrate_project_dir(project_dir) is False

    assert (project_dir / "project.json").read_bytes() == before
