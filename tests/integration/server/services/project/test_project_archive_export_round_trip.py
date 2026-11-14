"""导出的包都能导入，导入后每件产物的状态与源项目一致或更准，不因导出被洗成最新（ADR 0134）。"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from lib.artifacts.artifact_activation import ArtifactCurrencyResolver
from lib.artifacts.artifact_manifest import (
    MANIFEST_FILENAME,
    ArtifactKey,
    ArtifactStatus,
)
from lib.artifacts.version_manager import VersionManager
from lib.project.project_manager import ProjectManager
from lib.project.project_migrations.runner import migrate_project_with_verdict
from server.services.project.project_archive import (
    ProjectArchiveService,
    ProjectArchiveValidationError,
    ProjectImportResult,
)
from tests.legacy_project_shapes import drop_selected_version_snapshot, write_legacy_storyboard_project

_VIDEO = ArtifactKey.episode_video(1, "E1S1")
_VIDEO_PATH = "videos/scene_E1S1.mp4"
_STORYBOARD = ArtifactKey.episode_storyboard(1, "E1S1")
_STORYBOARD_PATH = "storyboards/scene_E1S1.png"
_SCOPES = ("full", "current")
_UPGRADE_LEFTOVER = "non_standard_entry_excluded"


def _current_project(root: Path) -> tuple[ProjectManager, Path]:
    project_dir = write_legacy_storyboard_project(root / "projects", name="demo")
    assert migrate_project_with_verdict(project_dir) is None
    return ProjectManager(root), project_dir


def _versions_path(project_dir: Path) -> Path:
    return project_dir / "versions" / "versions.json"


def _selected_record(project_dir: Path) -> dict:
    history = json.loads(_versions_path(project_dir).read_text(encoding="utf-8"))["videos"]["E1S1"]
    [record] = [item for item in history["versions"] if item["version"] == history["current_version"]]
    return record


def _rewrite_selected_record(project_dir: Path, **changes: object) -> None:
    versions = json.loads(_versions_path(project_dir).read_text(encoding="utf-8"))
    history = versions["videos"]["E1S1"]
    [record] = [item for item in history["versions"] if item["version"] == history["current_version"]]
    record.update(changes)
    _versions_path(project_dir).write_text(json.dumps(versions, ensure_ascii=False), encoding="utf-8")


def _edit_prompts(project_dir: Path) -> None:
    script_path = project_dir / "scripts" / "episode_1.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    script["segments"][0]["video_prompt"]["action"] = "改过的动作"
    script["segments"][0]["image_prompt"]["scene"] = "改过的画面"
    script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")


def _status(project_dir: Path, key: ArtifactKey, artifact_path: str) -> ArtifactStatus:
    return ArtifactCurrencyResolver(project_dir).compare(key, artifact_path=artifact_path).status


def _noticed(diagnostics: dict, bucket: str) -> list[tuple[str, str | None]]:
    return [(item["code"], item.get("location")) for item in diagnostics[bucket] if item["code"] != _UPGRADE_LEFTOVER]


def _round_trip(pm: ProjectManager, target_root: Path, scope: str = "full") -> tuple[dict, ProjectImportResult, Path]:
    """导出、导入；迁移报告非空时按用户确认后再导入。导出与导入都必须成功。"""
    service = ProjectArchiveService(pm)
    diagnostics = service.get_export_diagnostics("demo", scope=scope)
    archive_path, _ = service.export_project("demo", scope=scope)
    target = ProjectArchiveService(ProjectManager(target_root))
    try:
        result = target.import_project_archive(archive_path, uploaded_filename="demo.zip")
    except ProjectArchiveValidationError as exc:
        if not (exc.extra or {}).get("confirmation_required"):
            raise
        result = target.import_project_archive(archive_path, uploaded_filename="demo.zip", confirm_report=True)
    return diagnostics, result, ProjectManager(target_root).get_project_path(result.project_name)


# ---- P2-a：清单读不出时，按导出规划器自己的证明带信封 ----


def test_an_unreadable_manifest_keeps_stale_videos_stale_after_import(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    _edit_prompts(project_dir)
    (project_dir / MANIFEST_FILENAME).write_text("{ not json", encoding="utf-8")

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert _noticed(diagnostics, "warnings") == [("manifest_unreadable_exported_from_files", None)]
    # 视频照它版本记录里的生成依据判定：改过提示词就是已过期，不是缺失、也不是最新
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE
    assert _status(imported, ArtifactKey.episode_video(1, "E1S2"), "videos/scene_E1S2.mp4") is ArtifactStatus.CURRENT


# ---- P2-b：导出的包导入时不再被拒 ----


@pytest.mark.parametrize("scope", _SCOPES)
def test_a_storyboard_whose_file_is_gone_is_cleared_in_the_archive_so_it_imports(tmp_path: Path, scope: str) -> None:
    pm, project_dir = _current_project(tmp_path)
    (project_dir / _STORYBOARD_PATH).unlink()

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target", scope)

    assert diagnostics["blocking"] == []
    assert ("missing_reference_cleared", "scripts/episode_1.json:segments[0].generated_assets.storyboard_image") in (
        _noticed(diagnostics, "auto_fixed")
    )
    assert ("claim_left_out_missing", _STORYBOARD_PATH) in _noticed(diagnostics, "warnings")
    assert _status(imported, _STORYBOARD, _STORYBOARD_PATH) is ArtifactStatus.MISSING


def test_a_video_that_is_a_symlink_is_reported_as_unreadable_and_the_archive_imports(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes((project_dir / _VIDEO_PATH).read_bytes())
    (project_dir / _VIDEO_PATH).unlink()
    (project_dir / _VIDEO_PATH).symlink_to(outside)
    drop_selected_version_snapshot(project_dir, "videos", "E1S1")
    assert _status(project_dir, _VIDEO, _VIDEO_PATH) is ArtifactStatus.BLOCKED

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert diagnostics["blocking"] == []
    assert ("symlink_reference_cleared", "scripts/episode_1.json:segments[0].generated_assets.video_clip") in (
        _noticed(diagnostics, "auto_fixed")
    )
    assert ("claim_left_out_unreadable", _VIDEO_PATH) in _noticed(diagnostics, "warnings")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.MISSING


def test_a_version_record_outside_its_history_is_dropped_so_the_archive_imports(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    drop_selected_version_snapshot(project_dir, "videos", "E1S1")
    _rewrite_selected_record(project_dir, file="versions/videos/../../videos/scene_E1S2.mp4")

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert ("version_record_dropped", "videos/E1S1") in _noticed(diagnostics, "warnings")
    assert ("claim_carried_as_stale", _VIDEO_PATH) in _noticed(diagnostics, "warnings")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


@pytest.mark.parametrize("scope", _SCOPES)
def test_a_video_whose_file_and_snapshot_are_both_gone_imports_as_missing(tmp_path: Path, scope: str) -> None:
    pm, project_dir = _current_project(tmp_path)
    (project_dir / _VIDEO_PATH).unlink()
    drop_selected_version_snapshot(project_dir, "videos", "E1S1")

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target", scope)

    assert ("claim_left_out_missing", _VIDEO_PATH) in _noticed(diagnostics, "warnings")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.MISSING


# ---- P3-a：导入时快照缺失或损坏，告知用户并按指纹补回快照 ----


def _rezip_without(archive_path: Path, target: Path, member: str) -> Path:
    with zipfile.ZipFile(archive_path) as source, zipfile.ZipFile(target, "w") as rebuilt:
        for info in source.infolist():
            if info.filename != member:
                rebuilt.writestr(info, source.read(info))
    return target


def test_an_archive_missing_a_snapshot_imports_as_stale_tells_the_user_and_restores_the_version(
    tmp_path: Path,
) -> None:
    pm, project_dir = _current_project(tmp_path)
    snapshot_rel = _selected_record(project_dir)["file"]
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")
    stripped = _rezip_without(archive_path, tmp_path / "stripped.zip", f"demo/{snapshot_rel}")

    result = ProjectArchiveService(ProjectManager(tmp_path / "target")).import_project_archive(
        stripped, uploaded_filename="demo.zip"
    )
    imported = ProjectManager(tmp_path / "target").get_project_path(result.project_name)

    assert ("claim_imported_as_stale", _VIDEO_PATH) in _noticed(result.diagnostics, "warnings")
    assert ("version_snapshot_restored", snapshot_rel) in _noticed(result.diagnostics, "auto_fixed")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE
    assert (
        hashlib.sha256((imported / snapshot_rel).read_bytes()).hexdigest()
        == _selected_record(imported)["content_digest"]
    )
    VersionManager(imported).restore_version(
        "videos", "E1S1", _selected_record(imported)["version"], imported / _VIDEO_PATH
    )


# ---- P3-b：在场但损坏的快照按正式文件替换 ----


def test_a_corrupted_snapshot_is_replaced_so_a_current_video_stays_current(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    snapshot_rel = _selected_record(project_dir)["file"]
    (project_dir / snapshot_rel).write_bytes(b"corrupted snapshot")
    assert _status(project_dir, _VIDEO, _VIDEO_PATH) is ArtifactStatus.CURRENT

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert ("version_snapshot_restored", snapshot_rel) in _noticed(diagnostics, "auto_fixed")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.CURRENT
    # 源项目里那份坏快照原样不动
    assert (project_dir / snapshot_rel).read_bytes() == b"corrupted snapshot"


# ---- P3-c：已过期的视频不能经导出洗成最新 ----


def test_a_forged_version_digest_does_not_launder_a_stale_video(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    (project_dir / _VIDEO_PATH).write_bytes(b"replaced outside the app")
    drop_selected_version_snapshot(project_dir, "videos", "E1S1")
    _rewrite_selected_record(project_dir, content_digest=hashlib.sha256(b"replaced outside the app").hexdigest())
    assert _status(project_dir, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert ("claim_carried_as_stale", _VIDEO_PATH) in _noticed(diagnostics, "warnings")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


def test_a_formal_file_and_snapshot_replaced_together_do_not_launder_a_stale_video(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    (project_dir / _VIDEO_PATH).write_bytes(b"replaced outside the app")
    (project_dir / _selected_record(project_dir)["file"]).write_bytes(b"replaced outside the app")
    assert _status(project_dir, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert ("claim_carried_as_stale", _VIDEO_PATH) in _noticed(diagnostics, "warnings")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE
