"""迁移 runner：版本检测、最低版本、幂等、错误隔离、备份清理。"""

import json
import os
import time
from pathlib import Path

import pytest

from lib.project.project_migration_failure import (
    MIGRATION_FAILURE_FILENAME,
    ProjectMigrationError,
    load_migration_failure,
)
from lib.project.project_migrations.runner import (
    CURRENT_SCHEMA_VERSION,
    cleanup_stale_backups,
    migrate_project_dir,
    migrate_project_with_verdict,
    run_project_migrations,
)
from tests.factories import wrap_the_last_migration_step
from tests.legacy_project_shapes import SCHEMA_V19


@pytest.fixture
def tmp_projects(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    return root


def _write_project(root: Path, name: str, data: dict) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return d


def _write_v19_project_with_a_script_missing_its_episode(root: Path, name: str, schema_version: int | None) -> Path:
    """一集剧本顶层没写集号：链首规整会以账本绑定为准写回它。``schema_version`` 为 None 时不写该字段。"""
    project: dict = {"name": name, "episodes": [{"episode": 1, "script_file": "scripts/episode_1.json"}]}
    if schema_version is not None:
        project["schema_version"] = schema_version
    project_dir = _write_project(root, name, project)
    script = project_dir / "scripts" / "episode_1.json"
    script.parent.mkdir()
    script.write_text(json.dumps({"title": "第一集", "segments": []}, ensure_ascii=False), encoding="utf-8")
    return project_dir


def _tree(project_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project_dir).as_posix(): path.read_bytes() for path in project_dir.rglob("*") if path.is_file()
    }


def test_skip_already_current(tmp_projects: Path):
    _write_project(tmp_projects, "p1", {"schema_version": CURRENT_SCHEMA_VERSION, "name": "p1"})
    summary = run_project_migrations(tmp_projects)
    assert summary.migrated == []
    assert summary.skipped == ["p1"]


def test_a_v19_project_runs_the_last_step_once(tmp_projects: Path, monkeypatch):
    """v19 是迁移链能接的最早版本：runner 只跑 v19→v20 一步。"""
    _write_project(tmp_projects, "p1", {"schema_version": SCHEMA_V19, "name": "p1"})
    called: list[Path] = []

    def bump(_step, project_dir: Path, **_kwargs) -> None:
        called.append(project_dir)
        data = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
        data["schema_version"] = SCHEMA_V19 + 1
        (project_dir / "project.json").write_text(json.dumps(data), encoding="utf-8")

    wrap_the_last_migration_step(monkeypatch, bump)

    summary = run_project_migrations(tmp_projects)
    assert summary.migrated == ["p1"]
    assert called == [tmp_projects / "p1"]
    data = json.loads((tmp_projects / "p1" / "project.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == CURRENT_SCHEMA_VERSION


def test_a_v19_project_is_normalized_backed_up_and_migrated(tmp_projects: Path):
    """v19 → v20：链首规整照常跑，``project.json`` 改写前留一份 v19 备份。"""
    project_dir = _write_v19_project_with_a_script_missing_its_episode(tmp_projects, "p1", SCHEMA_V19)
    original = (project_dir / "project.json").read_bytes()

    assert migrate_project_dir(project_dir) is True

    data = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == CURRENT_SCHEMA_VERSION
    script = json.loads((project_dir / "scripts" / "episode_1.json").read_text(encoding="utf-8"))
    assert script["episode"] == 1
    assert [path.read_bytes() for path in project_dir.glob("project.json.bak.v19-*")] == [original]
    # 幂等：已是最新版本再调返回 False、不改动
    assert migrate_project_dir(project_dir) is False


@pytest.mark.parametrize("schema_version", [18, 0, None], ids=["v18", "v0", "without-schema-version"])
def test_a_project_older_than_schema_19_is_refused_before_anything_is_written(
    tmp_projects: Path, schema_version: int | None
):
    """更早的项目在规整与任何备份之前就被拒绝：目录里一个字节都不变，拒绝点名 ``project.json``。"""
    project_dir = _write_v19_project_with_a_script_missing_its_episode(tmp_projects, "old", schema_version)
    before = _tree(project_dir)

    with pytest.raises(ProjectMigrationError) as exc_info:
        migrate_project_dir(project_dir)

    assert exc_info.value.file == "project.json"
    assert _tree(project_dir) == before


def test_the_startup_run_blocks_a_project_older_than_schema_19_and_keeps_going(tmp_projects: Path):
    old = _write_v19_project_with_a_script_missing_its_episode(tmp_projects, "a-old", 18)
    _write_project(tmp_projects, "b-v19", {"schema_version": SCHEMA_V19, "name": "b-v19"})
    project_json = (old / "project.json").read_bytes()

    summary = run_project_migrations(tmp_projects)

    assert summary.failed == ["a-old"]
    assert summary.migrated == ["b-v19"]
    failure = load_migration_failure(old)
    assert failure is not None
    assert failure.schema_version == 18
    # 一次真实的失败尝试，不是「还没迁移」的待定裁决。
    assert failure.failed_at
    assert [(detail.episode, detail.file) for detail in failure.details] == [(None, "project.json")]
    assert (old / "project.json").read_bytes() == project_json
    assert list(old.glob("*.bak.v*")) == []


def test_a_project_without_schema_version_is_recorded_as_failed(tmp_projects: Path):
    """显式 null 与字段缺失同义（v0），在迁移链之外：记一次失败，``schema_version`` 原样留着。"""
    project_dir = _write_project(tmp_projects, "p1", {"schema_version": None, "episodes": []})

    failure = migrate_project_with_verdict(project_dir)

    assert failure is not None
    assert failure.schema_version == 0
    assert (project_dir / MIGRATION_FAILURE_FILENAME).is_file()
    assert json.loads((project_dir / "project.json").read_text(encoding="utf-8"))["schema_version"] is None


def test_skip_non_project_dirs(tmp_projects: Path):
    (tmp_projects / "global_assets").mkdir()
    (tmp_projects / "global_assets" / "keep.txt").write_text("x", encoding="utf-8")
    _write_project(tmp_projects, "p1", {"schema_version": CURRENT_SCHEMA_VERSION, "name": "p1"})
    summary = run_project_migrations(tmp_projects)
    assert "global_assets" not in summary.skipped
    assert "global_assets" not in summary.migrated


def test_corrupted_schema_version_skipped_not_abort(tmp_projects: Path):
    """schema_version 不可解析的项目按损坏跳过：不盖戳、不中断其他项目迁移。"""
    _write_project(tmp_projects, "broken", {"schema_version": "corrupted"})
    _write_project(tmp_projects, "ok", {"schema_version": SCHEMA_V19, "name": "ok"})

    summary = run_project_migrations(tmp_projects)

    assert "broken" not in summary.migrated + summary.failed + summary.skipped
    assert "ok" in summary.migrated
    data = json.loads((tmp_projects / "broken" / "project.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == "corrupted"  # 原样保留，待人工修复


def test_numeric_string_schema_version_is_not_classified_as_current(tmp_projects: Path):
    """数字字符串也是损坏的持久化版本，不能被误判为已完成迁移。"""
    _write_project(tmp_projects, "numeric-string", {"schema_version": str(CURRENT_SCHEMA_VERSION)})

    summary = run_project_migrations(tmp_projects)

    assert "numeric-string" not in summary.migrated + summary.failed + summary.skipped


def test_falsy_or_bool_schema_version_skipped_not_v0(tmp_projects: Path):
    """空串 / bool 等不可解析版本号按损坏跳过，不误当 v0 记失败。"""
    for name, bad in [("empty", ""), ("bool-true", True), ("bool-false", False)]:
        _write_project(tmp_projects, name, {"schema_version": bad})

    summary = run_project_migrations(tmp_projects)

    for name in ("empty", "bool-true", "bool-false"):
        assert name not in summary.migrated + summary.failed + summary.skipped


def test_error_isolated_not_abort(tmp_projects: Path, monkeypatch):
    _write_project(tmp_projects, "broken", {"schema_version": SCHEMA_V19, "name": "broken"})
    _write_project(tmp_projects, "ok", {"schema_version": CURRENT_SCHEMA_VERSION, "name": "ok"})

    def bad(_step, _project_dir, **_kwargs):
        raise RuntimeError("boom")

    wrap_the_last_migration_step(monkeypatch, bad)
    summary = run_project_migrations(tmp_projects)
    assert "broken" in summary.failed
    assert "ok" in summary.skipped


def _age(path: Path, days: int = 8) -> None:
    expired = time.time() - days * 86400
    os.utime(path, (expired, expired))


def test_cleanup_old_backups(tmp_projects: Path):
    p = _write_project(
        tmp_projects,
        "p1",
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "episodes": [{"episode": 1, "script_file": "scripts/episode_1.json"}],
        },
    )
    old = p / "project.json.bak.v19-100000000"
    new = p / "project.json.bak.v19-9999999999"
    old.write_text("old", encoding="utf-8")
    new.write_text("new", encoding="utf-8")
    old_script = p / "scripts" / "episode_1.json.bak.v19-100000000"
    new_manifest = p / ".arcreel_artifacts.json.bak.v19-9999999999"
    old_script.parent.mkdir()
    old_script.write_text("old-script", encoding="utf-8")
    new_manifest.write_text("new-manifest", encoding="utf-8")
    user_source = p / "source" / "novel.bak.v19-final.txt"
    user_source.parent.mkdir()
    user_source.write_text("user-owned", encoding="utf-8")

    for path in (old, old_script, user_source):
        _age(path)

    cleanup_stale_backups(tmp_projects, max_age_days=7)
    assert not old.exists()
    assert new.exists()
    assert not old_script.exists()
    assert new_manifest.exists()
    assert user_source.read_text(encoding="utf-8") == "user-owned"


def test_cleanup_retains_v19_recovery_backups_until_schema_promotion_succeeds(tmp_projects: Path) -> None:
    project_dir = _write_project(
        tmp_projects,
        "p1",
        {
            "schema_version": SCHEMA_V19,
            "episodes": [{"episode": 1, "script_file": "scripts/episode_1.json"}],
        },
    )
    backups = [
        project_dir / "project.json.bak.v19-100000000",
        project_dir / "scripts" / "episode_1.json.bak.v19-100000000",
        project_dir / ".arcreel_artifacts.json.bak.v19-100000000",
    ]
    for backup in backups:
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text("recovery", encoding="utf-8")
        _age(backup)

    cleanup_stale_backups(tmp_projects, max_age_days=7)

    assert all(backup.exists() for backup in backups)


def test_cleanup_reclaims_the_script_plan_draft_backups_the_normalization_leaves_behind(tmp_projects: Path) -> None:
    """链首规整改写草稿前为它落版本化备份，回收侧必须逐个覆盖，否则它们永久残留。"""
    project_dir = _write_project(
        tmp_projects,
        "p1",
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "episodes": [{"episode": 1, "script_file": "scripts/episode_1.json"}],
        },
    )
    drafts_dir = project_dir / "drafts" / "episode_1"
    drafts_dir.mkdir(parents=True)
    backups = [
        drafts_dir / "script_plan_segments.json.bak.v19-100000000",
        drafts_dir / "script_plan_normalized_script.json.bak.v19-100000000",
        drafts_dir / "script_plan_reference_units.json.bak.v19-100000000",
        project_dir / ".arcreel_artifacts.json.bak.v19-100000000",
    ]
    for backup in backups:
        backup.write_text("stale", encoding="utf-8")
        _age(backup)

    cleanup_stale_backups(tmp_projects, max_age_days=7)

    assert [backup for backup in backups if backup.exists()] == []


def test_failed_retry_does_not_duplicate_an_identical_project_backup(tmp_projects: Path, monkeypatch):
    """同一起点版本、内容相同的 project.json 只留一份备份；内容变了才新增。"""
    p = _write_project(tmp_projects, "p1", {"schema_version": SCHEMA_V19, "name": "p1"})

    def bad(_step, _project_dir, **_kwargs):
        raise RuntimeError("boom")

    wrap_the_last_migration_step(monkeypatch, bad)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            migrate_project_dir(p)
    assert len(list(p.glob("project.json.bak.v19-*"))) == 1

    (p / "project.json").write_text(
        json.dumps({"schema_version": SCHEMA_V19, "name": "p1", "title": "改过"}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError):
        migrate_project_dir(p)
    backups = sorted(p.glob("project.json.bak.v19-*"))
    assert len(backups) == 2
    assert {b.read_bytes() for b in backups} == {
        json.dumps({"schema_version": SCHEMA_V19, "name": "p1"}, ensure_ascii=False).encode(),
        json.dumps({"schema_version": SCHEMA_V19, "name": "p1", "title": "改过"}).encode(),
    }
