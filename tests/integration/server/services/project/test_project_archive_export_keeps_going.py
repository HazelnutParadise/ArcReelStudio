"""导出只管导出：证明不了状态的产物不让导出失败，也不悄悄丢掉状态（ADR 0134）。"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest

from lib.artifacts.artifact_activation import ArtifactCurrencyResolver, ArtifactTargetStateChangedError
from lib.artifacts.artifact_manifest import (
    MANIFEST_FILENAME,
    ArtifactKey,
    ArtifactStatus,
    ProjectArtifactManifestAdapter,
)
from lib.artifacts.version_manager import VersionManager
from lib.final_cut.basis import current_video
from lib.infra.api_errors import ApiError
from lib.project.data_validator import DataValidator
from lib.project.project_manager import ProjectManager
from lib.project.project_migrations.runner import migrate_project_with_verdict
from server.services.project import project_archive as project_archive_module
from server.services.project.project_archive import (
    ARCHIVE_MANIFEST_NAME,
    ProjectArchiveService,
    ProjectArchiveValidationError,
)
from tests.legacy_project_shapes import (
    drop_selected_version_snapshot,
    write_legacy_storyboard_project,
    write_legacy_tts_narration_project,
)

_VIDEO = ArtifactKey.episode_video(1, "E1S1")
_VIDEO_PATH = "videos/scene_E1S1.mp4"
_STORYBOARD = ArtifactKey.episode_storyboard(1, "E1S1")
_SCOPES = ("full", "current")


def _current_project(root: Path) -> tuple[ProjectManager, Path]:
    project_dir = write_legacy_storyboard_project(root / "projects", name="demo")
    assert migrate_project_with_verdict(project_dir) is None
    return ProjectManager(root), project_dir


def _selected_record(project_dir: Path, resource_type: str, resource_id: str) -> dict:
    versions = json.loads((project_dir / "versions" / "versions.json").read_text(encoding="utf-8"))
    history = versions[resource_type][resource_id]
    [record] = [item for item in history["versions"] if item["version"] == history["current_version"]]
    return record


def _tree(project_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(project_dir).as_posix(): path.read_bytes() for path in project_dir.rglob("*") if path.is_file()
    }


def _envelope(archive_path: Path) -> dict:
    with zipfile.ZipFile(archive_path) as archive:
        return json.loads(archive.read(f"demo/{ARCHIVE_MANIFEST_NAME}"))


def _import(archive_path: Path, target_root: Path) -> tuple[ProjectManager, Path]:
    """导入；迁移报告非空时按用户确认后再导入。"""
    target = ProjectManager(target_root)
    service = ProjectArchiveService(target)
    try:
        result = service.import_project_archive(archive_path, uploaded_filename="demo.zip")
    except ProjectArchiveValidationError as exc:
        if not (exc.extra or {}).get("confirmation_required"):
            raise
        result = service.import_project_archive(archive_path, uploaded_filename="demo.zip", confirm_report=True)
    return target, target.get_project_path(result.project_name)


def _status(project_dir: Path, key: ArtifactKey, artifact_path: str) -> ArtifactStatus:
    return ArtifactCurrencyResolver(project_dir).compare(key, artifact_path=artifact_path).status


def _codes(diagnostics: dict, bucket: str) -> list[str]:
    return [item["code"] for item in diagnostics[bucket] if item["code"] != "non_standard_entry_excluded"]


def _warned(diagnostics: dict) -> list[tuple[str, str | None]]:
    """升级留下的 ``project.json.bak.*`` 照常报「非标准条目」，与这里无关。"""
    return [
        (item["code"], item.get("location"))
        for item in diagnostics["warnings"]
        if item["code"] != "non_standard_entry_excluded"
    ]


@pytest.mark.parametrize("scope", _SCOPES)
def test_export_rebuilds_a_missing_selected_video_snapshot_from_the_matching_formal_file(
    tmp_path: Path, scope: str
) -> None:
    pm, project_dir = _current_project(tmp_path)
    snapshot_rel = drop_selected_version_snapshot(project_dir, "videos", "E1S1")
    recorded = _selected_record(project_dir, "videos", "E1S1")["content_digest"]
    source_before = _tree(project_dir)
    service = ProjectArchiveService(pm)

    diagnostics = service.get_export_diagnostics("demo", scope=scope)
    archive_path, _ = service.export_project("demo", scope=scope)

    assert _codes(diagnostics, "auto_fixed") == ["version_snapshot_restored"]
    assert diagnostics["auto_fixed"][0]["location"] == snapshot_rel
    with zipfile.ZipFile(archive_path) as archive:
        assert hashlib.sha256(archive.read(f"demo/{snapshot_rel}")).hexdigest() == recorded
    assert _VIDEO.encode() in _envelope(archive_path)["artifact_manifest"]["entries"]
    # 只补导出副本，源项目一个字节都不动
    assert _tree(project_dir) == source_before


@pytest.mark.parametrize("scope", _SCOPES)
def test_import_of_a_rebuilt_snapshot_reads_current_and_the_version_is_usable(tmp_path: Path, scope: str) -> None:
    pm, project_dir = _current_project(tmp_path)
    drop_selected_version_snapshot(project_dir, "videos", "E1S1")
    recorded = _selected_record(project_dir, "videos", "E1S1")["content_digest"]
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope=scope)

    _, imported = _import(archive_path, tmp_path / "target")

    entry = ProjectArtifactManifestAdapter(imported).snapshot_entries()[_VIDEO]
    assert entry.content is not None
    assert entry.content.digest == recorded
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.CURRENT
    versions = VersionManager(imported)
    assert current_video(imported, versions, "videos", "E1S1", lambda _rel: "unused") is not None
    record = _selected_record(imported, "videos", "E1S1")
    versions.restore_version("videos", "E1S1", record["version"], imported / _VIDEO_PATH)


def test_export_rebuilds_a_missing_selected_audio_snapshot(tmp_path: Path) -> None:
    project_dir = write_legacy_tts_narration_project(tmp_path / "projects", name="demo")
    assert migrate_project_with_verdict(project_dir) is None
    audio_key = ArtifactKey.episode_audio(1, "E1S2")
    assert ProjectArtifactManifestAdapter(project_dir).snapshot_entries()[audio_key].content is not None
    snapshot_rel = drop_selected_version_snapshot(project_dir, "audio", "E1S2")
    service = ProjectArchiveService(ProjectManager(tmp_path))

    diagnostics = service.get_export_diagnostics("demo", scope="full")
    archive_path, _ = service.export_project("demo", scope="full")
    _, imported = _import(archive_path, tmp_path / "target")

    assert [item["location"] for item in diagnostics["auto_fixed"]] == [snapshot_rel]
    assert _status(imported, audio_key, "audio/segment_E1S2.wav") is ArtifactStatus.CURRENT


def test_export_rebuilds_a_missing_storyboard_snapshot_with_a_recorded_digest(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    VersionManager(project_dir).add_version(
        "storyboards", "E1S1", "画面 1", source_file=project_dir / "storyboards" / "scene_E1S1.png"
    )
    snapshot_rel = drop_selected_version_snapshot(project_dir, "storyboards", "E1S1")
    service = ProjectArchiveService(pm)

    diagnostics = service.get_export_diagnostics("demo", scope="full")
    archive_path, _ = service.export_project("demo", scope="full")
    _, imported = _import(archive_path, tmp_path / "target")

    assert [item["location"] for item in diagnostics["auto_fixed"]] == [snapshot_rel]
    assert (imported / snapshot_rel).is_file()
    # 仅当前版本的包不带分镜历史：不补，也不报
    assert ProjectArchiveService(pm).get_export_diagnostics("demo", scope="current")["auto_fixed"] == []


@pytest.mark.parametrize("scope", _SCOPES)
def test_a_formal_file_that_no_longer_matches_its_version_travels_as_stale(tmp_path: Path, scope: str) -> None:
    pm, project_dir = _current_project(tmp_path)
    snapshot_rel = drop_selected_version_snapshot(project_dir, "videos", "E1S1")
    (project_dir / _VIDEO_PATH).write_bytes(b"replaced outside the app")
    assert _status(project_dir, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE
    service = ProjectArchiveService(pm)

    diagnostics = service.get_export_diagnostics("demo", scope=scope)
    archive_path, _ = service.export_project("demo", scope=scope)
    _, imported = _import(archive_path, tmp_path / "target")

    # 对不上记录指纹的正式文件不拿来补快照
    with zipfile.ZipFile(archive_path) as archive:
        assert f"demo/{snapshot_rel}" not in archive.namelist()
    assert diagnostics["auto_fixed"] == []
    assert _warned(diagnostics) == [("claim_carried_as_stale", _VIDEO_PATH)]
    entry = ProjectArtifactManifestAdapter(imported).snapshot_entries()[_VIDEO]
    assert entry.content is None
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


def test_an_externally_replaced_video_with_its_snapshot_present_exports_as_stale(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    (project_dir / _VIDEO_PATH).write_bytes(b"replaced outside the app")
    service = ProjectArchiveService(pm)

    archive_path, _ = service.export_project("demo", scope="full")
    _, imported = _import(archive_path, tmp_path / "target")

    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


def test_a_video_whose_version_history_is_gone_exports_as_stale(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    versions_path = project_dir / "versions" / "versions.json"
    versions = json.loads(versions_path.read_text(encoding="utf-8"))
    del versions["videos"]["E1S1"]
    versions_path.write_text(json.dumps(versions), encoding="utf-8")
    service = ProjectArchiveService(pm)

    diagnostics = service.get_export_diagnostics("demo", scope="full")
    archive_path, _ = service.export_project("demo", scope="full")
    _, imported = _import(archive_path, tmp_path / "target")

    assert _warned(diagnostics) == [("claim_carried_as_stale", _VIDEO_PATH)]
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


@pytest.mark.parametrize("scope", _SCOPES)
def test_a_claim_whose_formal_file_is_gone_is_left_out_with_a_warning(tmp_path: Path, scope: str) -> None:
    pm, project_dir = _current_project(tmp_path)
    (project_dir / "storyboards" / "scene_E1S1.png").unlink()
    assert _status(project_dir, _STORYBOARD, "storyboards/scene_E1S1.png") is ArtifactStatus.MISSING
    service = ProjectArchiveService(pm)

    diagnostics = service.get_export_diagnostics("demo", scope=scope)
    archive_path, _ = service.export_project("demo", scope=scope)

    assert _warned(diagnostics) == [("claim_left_out_missing", "storyboards/scene_E1S1.png")]
    entries = _envelope(archive_path)["artifact_manifest"]["entries"]
    assert _STORYBOARD.encode() not in entries
    assert _VIDEO.encode() in entries


def test_an_unreadable_manifest_exports_from_the_files_and_imports(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    (project_dir / MANIFEST_FILENAME).write_text("{ not json", encoding="utf-8")
    service = ProjectArchiveService(pm)

    diagnostics = service.get_export_diagnostics("demo", scope="full")
    archive_path, _ = service.export_project("demo", scope="full")
    _, imported = _import(archive_path, tmp_path / "target")

    assert _warned(diagnostics) == [("manifest_unreadable_exported_from_files", None)]
    assert _VIDEO.encode() in _envelope(archive_path)["artifact_manifest"]["entries"]
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.CURRENT


def test_archive_formal_bytes_changed_without_the_envelope_are_still_refused(tmp_path: Path) -> None:
    pm, _project_dir = _current_project(tmp_path)
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive_path) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            data = source.read(info)
            target.writestr(info, b"swapped inside the zip" if info.filename == f"demo/{_VIDEO_PATH}" else data)

    with pytest.raises(ProjectArchiveValidationError) as exc:
        ProjectArchiveService(ProjectManager(tmp_path / "target")).import_project_archive(
            tampered, uploaded_filename="demo.zip"
        )
    assert [message.key for message in exc.value.errors] == ["arch_artifact_activation_failed"]


def test_an_unreadable_script_stops_the_export_with_a_localised_reason(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    (project_dir / "scripts" / "episode_1.json").write_text("{ not json", encoding="utf-8")

    with pytest.raises(ApiError) as exc:
        ProjectArchiveService(pm).export_project("demo", scope="full")

    assert (exc.value.status_code, exc.value.key) == (422, "export_project_unreadable_at")


class _ChurningArchiveService(ProjectArchiveService):
    """每次复制完快照，源项目就又被写了一笔：模拟导出期间一直有任务在写文件。"""

    def _copy_visible_tree(self, source_dir: Path, target_dir: Path) -> tuple[tuple[str, str], ...]:
        copied = super()._copy_visible_tree(source_dir, target_dir)
        churn = source_dir / "source" / "churn.txt"
        with churn.open("a", encoding="utf-8") as stream:
            stream.write("+")
        return copied


def test_a_project_that_keeps_changing_stops_the_export_as_a_conflict(tmp_path: Path) -> None:
    pm, _project_dir = _current_project(tmp_path)

    with pytest.raises(ApiError) as exc:
        _ChurningArchiveService(pm).export_project("demo", scope="full")

    assert (exc.value.status_code, exc.value.key) == (409, "export_project_busy")


def _unreadable(project_dir: Path) -> tuple[int, str, object]:
    with pytest.raises(ApiError) as exc:
        ProjectArchiveService(ProjectManager(project_dir.parent.parent)).export_project("demo", scope="full")
    return exc.value.status_code, exc.value.key, exc.value.diagnostic


_RUNS_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


@pytest.mark.skipif(_RUNS_AS_ROOT, reason="root 不受文件权限限制，读不出的文件做不出来")
@pytest.mark.parametrize("relative", ["videos/scene_E1S1.mp4", "scripts"])
def test_a_file_or_directory_the_export_cannot_read_stops_with_its_location(tmp_path: Path, relative: str) -> None:
    _pm, project_dir = _current_project(tmp_path)
    target = project_dir / relative
    target.chmod(0)
    try:
        assert _unreadable(project_dir) == (422, "export_project_unreadable_at", relative)
    finally:
        target.chmod(0o755)


def test_a_script_that_is_not_an_object_stops_the_export_with_its_location(tmp_path: Path) -> None:
    _pm, project_dir = _current_project(tmp_path)
    (project_dir / "scripts" / "episode_1.json").write_text("[]", encoding="utf-8")

    assert _unreadable(project_dir) == (422, "export_project_unreadable_at", "scripts/episode_1.json (episode 1)")


@pytest.mark.parametrize("payload", ["{ not json", "[]"])
def test_unreadable_version_history_names_its_own_file(tmp_path: Path, payload: str) -> None:
    _pm, project_dir = _current_project(tmp_path)
    (project_dir / "versions" / "versions.json").write_text(payload, encoding="utf-8")

    assert _unreadable(project_dir) == (422, "export_project_unreadable_at", "versions/versions.json")


def test_export_diagnostics_for_an_unparseable_project_name_no_server_paths(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    (project_dir / "project.json").write_text("{ not json", encoding="utf-8")

    diagnostics = ProjectArchiveService(pm).get_export_diagnostics("demo", scope="full")

    messages = [item["message"] for item in diagnostics["blocking"]]
    assert messages
    assert all("project.json" in message and "/" not in message.replace("project.json", "") for message in messages)


class _DiskFullArchiveService(ProjectArchiveService):
    """写导出副本时磁盘写满。"""

    def _copy_visible_tree(self, source_dir: Path, target_dir: Path) -> tuple[tuple[str, str], ...]:
        raise OSError(errno.ENOSPC, "No space left on device", str(target_dir / "videos" / "scene_E1S1.mp4"))


class _DirectoryReplacedOnceArchiveService(ProjectArchiveService):
    """第一次复制时一个目录正好被换成同名文件，之后项目恢复平静。"""

    attempts = 0

    def _copy_visible_tree(self, source_dir: Path, target_dir: Path) -> tuple[tuple[str, str], ...]:
        type(self).attempts += 1
        if type(self).attempts == 1:
            raise NotADirectoryError(errno.ENOTDIR, "Not a directory", str(source_dir / "videos"))
        return super()._copy_visible_tree(source_dir, target_dir)


def test_a_full_disk_stops_the_export_with_its_own_reason(tmp_path: Path) -> None:
    pm, _project_dir = _current_project(tmp_path)

    with pytest.raises(ApiError) as exc:
        _DiskFullArchiveService(pm).export_project("demo", scope="full")

    assert (exc.value.status_code, exc.value.key) == (507, "export_disk_full")


def test_a_directory_replaced_while_copying_is_retried_like_a_vanished_file(tmp_path: Path) -> None:
    pm, _project_dir = _current_project(tmp_path)

    archive_path, _ = _DirectoryReplacedOnceArchiveService(pm).export_project("demo", scope="full")

    assert archive_path.is_file()
    assert _DirectoryReplacedOnceArchiveService.attempts == 2


def test_inputs_changing_while_the_archive_is_planned_stop_the_export_as_a_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pm, _project_dir = _current_project(tmp_path)

    def _changed(*_args: object, **_kwargs: object) -> None:
        raise ArtifactTargetStateChangedError("artifact activation dependency changed after preflight: videos")

    monkeypatch.setattr(project_archive_module, "snapshot_preserved_artifact_manifest", _changed)

    with pytest.raises(ApiError) as exc:
        ProjectArchiveService(pm).export_project("demo", scope="full")

    assert (exc.value.status_code, exc.value.key) == (409, "export_project_busy")


@pytest.mark.parametrize("payload", ["[]", "3", '"x"', "null"])
def test_a_project_file_that_is_not_an_object_is_reported_not_crashed(tmp_path: Path, payload: str) -> None:
    pm, project_dir = _current_project(tmp_path)
    (project_dir / "project.json").write_text(payload, encoding="utf-8")

    diagnostics = ProjectArchiveService(pm).get_export_diagnostics("demo", scope="full")

    assert [item["code"] for item in diagnostics["blocking"]][:1] == ["invalid_project_json"]


def test_validating_one_episode_file_names_it_relative_to_the_project(tmp_path: Path) -> None:
    _pm, project_dir = _current_project(tmp_path)
    (project_dir / "scripts" / "episode_1.json").write_text("[]", encoding="utf-8")
    validator = DataValidator()

    results = [
        validator.validate_episode_file(project_dir, "scripts/episode_1.json"),
        validator.validate_episode_file(project_dir, "scripts/episode_9.json"),
    ]

    assert [str(message.params["path"]) for result in results for message in result.error_messages] == [
        "scripts/episode_1.json",
        "scripts/episode_9.json",
    ]


def test_a_snapshot_path_that_is_a_directory_stops_the_export_with_its_location(tmp_path: Path) -> None:
    _pm, project_dir = _current_project(tmp_path)
    snapshot_rel = drop_selected_version_snapshot(project_dir, "videos", "E1S1")
    (project_dir / snapshot_rel).mkdir()
    (project_dir / snapshot_rel / "inner").write_bytes(b"x")

    assert _unreadable(project_dir) == (422, "export_project_unreadable_at", snapshot_rel)


class _QuotaExceededArchiveService(ProjectArchiveService):
    """写导出副本时超出磁盘配额。"""

    def _copy_visible_tree(self, source_dir: Path, target_dir: Path) -> tuple[tuple[str, str], ...]:
        raise OSError(errno.EDQUOT, "Disc quota exceeded", str(target_dir / "videos" / "scene_E1S1.mp4"))


@pytest.mark.parametrize("service_type", [_DiskFullArchiveService, _QuotaExceededArchiveService])
@pytest.mark.parametrize("entry", ["export_project", "get_export_diagnostics"])
def test_running_out_of_disk_space_stops_every_export_entry_with_its_own_reason(
    tmp_path: Path, service_type: type[ProjectArchiveService], entry: str
) -> None:
    pm, _project_dir = _current_project(tmp_path)

    with pytest.raises(ApiError) as exc:
        getattr(service_type(pm), entry)("demo", scope="full")

    assert (exc.value.status_code, exc.value.key) == (507, "export_disk_full")


def test_an_unreadable_location_is_part_of_the_message_the_user_sees(tmp_path: Path) -> None:
    _pm, project_dir = _current_project(tmp_path)
    (project_dir / "scripts" / "episode_1.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ApiError) as exc:
        ProjectArchiveService(ProjectManager(tmp_path)).export_project("demo", scope="full")

    assert exc.value.key == "export_project_unreadable_at"
    assert exc.value.params == {"location": "scripts/episode_1.json (episode 1)"}
