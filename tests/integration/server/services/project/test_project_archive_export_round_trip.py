"""导出的包都能导入，导入后每件产物的状态与源项目一致或更准，不因导出被洗成最新（ADR 0134）。"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from lib.artifacts.artifact_activation import UNPROVEN_MEDIA_BASIS_DIGEST, ArtifactCurrencyResolver
from lib.artifacts.artifact_manifest import (
    MANIFEST_FILENAME,
    ArtifactKey,
    ArtifactStatus,
    ProjectArtifactManifestAdapter,
)
from lib.artifacts.version_manager import VersionManager
from lib.artifacts.video_artifact_commit import commit_paid_video_artifact
from lib.artifacts.video_artifact_facts import VideoArtifactCurrencyFacts
from lib.material.storage import VersionSnapshotCorruptedError
from lib.project.project_manager import ProjectManager
from lib.project.project_migrations.runner import migrate_project_with_verdict
from server.services.currency.typed_media_restore import restore_typed_media_resource
from server.services.project.project_archive import (
    ARCHIVE_MANIFEST_NAME,
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

    # 导出不按被改过的版本记录给包里补一份「版本文件」
    assert not [code for code, _ in _noticed(diagnostics, "auto_fixed") if code == "version_snapshot_restored"]
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


# ---- 第二轮：导入后 stale 的媒体不会在下一次导出导入时变成最新 ----


def _rezip_with(archive_path: Path, target: Path, replacements: dict[str, bytes | None]) -> Path:
    with zipfile.ZipFile(archive_path) as source, zipfile.ZipFile(target, "w") as rebuilt:
        for info in source.infolist():
            if info.filename in replacements:
                data = replacements[info.filename]
                if data is not None:
                    rebuilt.writestr(info, data)
            else:
                rebuilt.writestr(info, source.read(info))
    return target


def _import_archive(archive_path: Path, target_root: Path) -> tuple[ProjectManager, ProjectImportResult]:
    target = ProjectManager(target_root)
    service = ProjectArchiveService(target)
    try:
        result = service.import_project_archive(archive_path, uploaded_filename="demo.zip")
    except ProjectArchiveValidationError as exc:
        if not (exc.extra or {}).get("confirmation_required"):
            raise
        result = service.import_project_archive(archive_path, uploaded_filename="demo.zip", confirm_report=True)
    return target, result


def _forged_archive(pm: ProjectManager, tmp_path: Path, project_dir: Path) -> Path:
    """改写包：正式文件换成别的字节，信封指纹与版本记录的指纹都改成它，原来那份正确的快照留着。"""
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")
    forged = b"bytes that never were this version"
    with zipfile.ZipFile(archive_path) as archive:
        envelope = json.loads(archive.read(f"demo/{ARCHIVE_MANIFEST_NAME}"))
        versions = json.loads(archive.read("demo/versions/versions.json"))
    history = versions["videos"]["E1S1"]
    [record] = [item for item in history["versions"] if item["version"] == history["current_version"]]
    record["content_digest"] = hashlib.sha256(forged).hexdigest()
    envelope["artifact_manifest"]["entries"][_VIDEO.encode()]["content_digest"] = hashlib.sha256(forged).hexdigest()
    return _rezip_with(
        archive_path,
        tmp_path / "forged.zip",
        {
            f"demo/{_VIDEO_PATH}": forged,
            "demo/versions/versions.json": json.dumps(versions).encode(),
            f"demo/{ARCHIVE_MANIFEST_NAME}": json.dumps(envelope).encode(),
        },
    )


@pytest.mark.parametrize("damage", ["drop_snapshot", "forged_digest"])
def test_a_video_imported_as_stale_stays_stale_after_a_second_export_and_import(tmp_path: Path, damage: str) -> None:
    pm, project_dir = _current_project(tmp_path)
    if damage == "drop_snapshot":
        archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")
        first = _rezip_with(
            archive_path, tmp_path / "first.zip", {f"demo/{_selected_record(project_dir)['file']}": None}
        )
    else:
        first = _forged_archive(pm, tmp_path, project_dir)
    hop1, imported_once = _import_archive(first, tmp_path / "hop1")
    once = hop1.get_project_path(imported_once.project_name)
    assert _status(once, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE

    diagnostics, _, twice = _round_trip(hop1, tmp_path / "hop2")

    assert ("claim_carried_as_stale", _VIDEO_PATH) in _noticed(diagnostics, "warnings")
    assert _status(twice, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


def test_a_video_whose_file_snapshot_and_record_were_all_replaced_stays_stale(tmp_path: Path) -> None:
    """只有源清单的内容事实还记着原来那一版：正式文件、快照与版本记录指纹被一起改成一致，也不按它们证明。"""
    pm, project_dir = _current_project(tmp_path)
    replaced = b"replaced outside the app"
    (project_dir / _VIDEO_PATH).write_bytes(replaced)
    (project_dir / _selected_record(project_dir)["file"]).write_bytes(replaced)
    _rewrite_selected_record(project_dir, content_digest=hashlib.sha256(replaced).hexdigest())
    assert _status(project_dir, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert ("claim_carried_as_stale", _VIDEO_PATH) in _noticed(diagnostics, "warnings")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


# ---- 第二轮：清单读不出时，证明不了或没有版本记录的视频仍判 stale ----


@pytest.mark.parametrize("damage", ["formal_replaced", "no_version_record"])
def test_an_unreadable_manifest_carries_an_unprovable_video_as_stale(tmp_path: Path, damage: str) -> None:
    pm, project_dir = _current_project(tmp_path)
    if damage == "formal_replaced":
        (project_dir / _VIDEO_PATH).write_bytes(b"replaced outside the app")
    else:
        versions = json.loads(_versions_path(project_dir).read_text(encoding="utf-8"))
        del versions["videos"]["E1S1"]
        _versions_path(project_dir).write_text(json.dumps(versions), encoding="utf-8")
    (project_dir / MANIFEST_FILENAME).write_text("{ not json", encoding="utf-8")

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert ("claim_carried_as_stale", _VIDEO_PATH) in _noticed(diagnostics, "warnings")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


# ---- 第二轮：导入校验要求的每个引用，在导出的包里不是在场就是已清空 ----


def _point_every_reference_at_a_file(project_dir: Path) -> None:
    """让项目里导入校验会检查的每一类引用都指向一个存在的文件。"""
    script_path = project_dir / "scripts" / "episode_1.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    segment = script["segments"][0]
    for relative in ("end_frames/E1S1_end.png", "videos/E1S1_uri.mp4", "storyboards/E1S1_last.png"):
        (project_dir / relative).parent.mkdir(parents=True, exist_ok=True)
        (project_dir / relative).write_bytes(relative.encode())
    segment["end_frame_image"] = "end_frames/E1S1_end.png"
    segment["generated_assets"]["video_uri"] = "videos/E1S1_uri.mp4"
    segment["generated_assets"]["storyboard_last_image"] = "storyboards/E1S1_last.png"
    script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    project["style_image"] = "style_reference.png"
    (project_dir / "style_reference.png").write_bytes(b"style")
    for bucket, field_name, relative in (
        ("characters", "character_sheet", "characters/Hero.png"),
        ("characters", "reference_image", "characters/refs/Hero.png"),
        ("characters", "reference_audio", "characters/refs_audio/Hero.wav"),
        ("scenes", "scene_sheet", "scenes/Temple.png"),
        ("props", "prop_sheet", "props/Key.png"),
    ):
        name = relative.rsplit("/", 1)[1].split(".")[0]
        project.setdefault(bucket, {}).setdefault(name, {"description": name})[field_name] = relative
        (project_dir / relative).parent.mkdir(parents=True, exist_ok=True)
        (project_dir / relative).write_bytes(relative.encode())
    (project_dir / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")


def test_every_reference_the_import_requires_is_present_or_cleared_in_the_archive(tmp_path: Path) -> None:
    """不按字段清单举例：删掉项目里除 JSON 外的全部文件，导出的包仍必须通过导入校验并导入成功。"""
    pm, project_dir = _current_project(tmp_path)
    _point_every_reference_at_a_file(project_dir)
    for path in sorted(project_dir.rglob("*"), reverse=True):
        if path.is_file() and path.suffix != ".json" and not path.name.startswith("."):
            path.unlink()

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert diagnostics["blocking"] == []
    cleared = {
        location for code, location in _noticed(diagnostics, "auto_fixed") if code == "missing_reference_cleared"
    }
    assert {
        "scripts/episode_1.json:segments[0].end_frame_image",
        "scripts/episode_1.json:segments[0].generated_assets.video_uri",
        "project.json:characters[Hero].reference_audio",
    } <= cleared
    assert ProjectArchiveService(ProjectManager(tmp_path / "target")).validator.validate_project_tree(imported).valid


@pytest.mark.parametrize(
    ("field_path", "value"),
    [(("end_frame_image",), "end_frames/E1S1_end.png"), (("generated_assets", "video_uri"), "videos/gone.mp4")],
)
def test_a_dangling_end_frame_or_local_video_uri_is_cleared_so_the_archive_imports(
    tmp_path: Path, field_path: tuple[str, ...], value: str
) -> None:
    pm, project_dir = _current_project(tmp_path)
    script_path = project_dir / "scripts" / "episode_1.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    holder = script["segments"][0]
    for part in field_path[:-1]:
        holder = holder[part]
    holder[field_path[-1]] = value
    script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    diagnostics, _, _ = _round_trip(pm, tmp_path / "target")

    assert ("missing_reference_cleared", f"scripts/episode_1.json:segments[0].{'.'.join(field_path)}") in _noticed(
        diagnostics, "auto_fixed"
    )


def test_a_bare_file_name_that_resolves_in_its_default_folder_is_kept(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    script_path = project_dir / "scripts" / "episode_1.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    script["segments"][0]["generated_assets"]["storyboard_image"] = "scene_E1S1.png"
    script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert not [location for code, location in _noticed(diagnostics, "auto_fixed") if "reference_cleared" in code]
    # 修复步骤把它规整成规范路径；引用照常在场，没有被当成悬空引用清空
    imported_script = json.loads((imported / "scripts" / "episode_1.json").read_text(encoding="utf-8"))
    assert imported_script["segments"][0]["generated_assets"]["storyboard_image"] == _STORYBOARD_PATH
    assert _status(imported, _STORYBOARD, _STORYBOARD_PATH) is not ArtifactStatus.MISSING


def test_a_symlinked_storyboard_folder_is_reported_as_unreadable(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    outside = tmp_path / "outside-storyboards"
    (project_dir / "storyboards").rename(outside)
    (project_dir / "storyboards").symlink_to(outside, target_is_directory=True)

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    warned = _noticed(diagnostics, "warnings")
    assert ("claim_left_out_unreadable", _STORYBOARD_PATH) in warned
    assert ("claim_left_out_missing", _STORYBOARD_PATH) not in warned
    assert ("symlink_reference_cleared", "scripts/episode_1.json:segments[0].generated_assets.storyboard_image") in (
        _noticed(diagnostics, "auto_fixed")
    )
    assert _status(imported, _STORYBOARD, _STORYBOARD_PATH) is ArtifactStatus.MISSING


# ---- 第二轮：版本记录结构损坏的桶照导入的判据去掉 ----


def test_a_version_bucket_that_is_not_an_object_is_dropped_so_the_archive_imports(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    versions = json.loads(_versions_path(project_dir).read_text(encoding="utf-8"))
    versions["characters"] = []
    _versions_path(project_dir).write_text(json.dumps(versions), encoding="utf-8")

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert ("version_history_malformed_dropped", "characters") in _noticed(diagnostics, "warnings")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.CURRENT


# ---- 第二轮：无信封的包在判时效前补快照 ----


def test_an_archive_without_an_envelope_restores_a_missing_snapshot_before_registering(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    snapshot_rel = _selected_record(project_dir)["file"]
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")
    with zipfile.ZipFile(archive_path) as archive:
        envelope = json.loads(archive.read(f"demo/{ARCHIVE_MANIFEST_NAME}"))
    envelope.pop("artifact_manifest")
    stripped = _rezip_with(
        archive_path,
        tmp_path / "no-envelope.zip",
        {f"demo/{snapshot_rel}": None, f"demo/{ARCHIVE_MANIFEST_NAME}": json.dumps(envelope).encode()},
    )

    target, result = _import_archive(stripped, tmp_path / "target")
    imported = target.get_project_path(result.project_name)

    assert ("version_snapshot_restored", snapshot_rel) in _noticed(result.diagnostics, "auto_fixed")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.CURRENT


def test_an_archive_whose_file_and_snapshot_were_replaced_together_imports_as_stale(tmp_path: Path) -> None:
    """包里的正式文件、快照与信封指纹被一起改成一致、版本记录没动：两者相同证明不了它是那个版本。"""
    pm, project_dir = _current_project(tmp_path)
    snapshot_rel = _selected_record(project_dir)["file"]
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")
    replaced = b"replaced inside the archive"
    with zipfile.ZipFile(archive_path) as archive:
        envelope = json.loads(archive.read(f"demo/{ARCHIVE_MANIFEST_NAME}"))
    envelope["artifact_manifest"]["entries"][_VIDEO.encode()]["content_digest"] = hashlib.sha256(replaced).hexdigest()
    tampered = _rezip_with(
        archive_path,
        tmp_path / "replaced.zip",
        {
            f"demo/{_VIDEO_PATH}": replaced,
            f"demo/{snapshot_rel}": replaced,
            f"demo/{ARCHIVE_MANIFEST_NAME}": json.dumps(envelope).encode(),
        },
    )

    target, result = _import_archive(tampered, tmp_path / "target")

    assert _status(target.get_project_path(result.project_name), _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


# ---- 第三轮：导入从不覆盖包里带来的快照 ----


def test_import_keeps_an_archived_snapshot_that_does_not_match_a_forged_record(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    snapshot_rel = _selected_record(project_dir)["file"]
    original_snapshot = (project_dir / snapshot_rel).read_bytes()

    target, result = _import_archive(_forged_archive(pm, tmp_path, project_dir), tmp_path / "target")
    imported = target.get_project_path(result.project_name)

    assert (imported / snapshot_rel).read_bytes() == original_snapshot
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE
    warned = _noticed(result.diagnostics, "warnings")
    assert ("claim_imported_as_stale_unrestorable", _VIDEO_PATH) in warned
    assert ("version_snapshot_mismatch_kept", snapshot_rel) in warned
    assert not [code for code, _ in _noticed(result.diagnostics, "auto_fixed") if code == "version_snapshot_restored"]
    # 切回这个版本时按版本记录校验快照：对不上就拒绝，登记仍是 stale
    record = _selected_record(imported)
    with pytest.raises(VersionSnapshotCorruptedError):
        VersionManager(imported).restore_version("videos", "E1S1", record["version"], imported / _VIDEO_PATH)
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


# ---- 第三轮：版本记录没有指纹时，按源清单登记的内容事实补快照（只在导出） ----


def test_export_rebuilds_a_snapshot_from_the_claims_content_facts_when_the_record_has_no_digest(
    tmp_path: Path,
) -> None:
    pm, project_dir = _current_project(tmp_path)
    snapshot_rel = drop_selected_version_snapshot(project_dir, "videos", "E1S1")
    versions = json.loads(_versions_path(project_dir).read_text(encoding="utf-8"))
    history = versions["videos"]["E1S1"]
    [record] = [item for item in history["versions"] if item["version"] == history["current_version"]]
    record.pop("content_digest")
    _versions_path(project_dir).write_text(json.dumps(versions), encoding="utf-8")
    assert _status(project_dir, _VIDEO, _VIDEO_PATH) is ArtifactStatus.CURRENT

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert ("version_snapshot_restored", snapshot_rel) in _noticed(diagnostics, "auto_fixed")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.CURRENT


def test_claim_facts_that_do_not_match_the_formal_file_never_rebuild_a_snapshot(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    drop_selected_version_snapshot(project_dir, "videos", "E1S1")
    versions = json.loads(_versions_path(project_dir).read_text(encoding="utf-8"))
    history = versions["videos"]["E1S1"]
    [record] = [item for item in history["versions"] if item["version"] == history["current_version"]]
    record.pop("content_digest")
    _versions_path(project_dir).write_text(json.dumps(versions), encoding="utf-8")
    (project_dir / _VIDEO_PATH).write_bytes(b"replaced outside the app")

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert not [code for code, _ in _noticed(diagnostics, "auto_fixed") if code == "version_snapshot_restored"]
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


def test_import_never_rebuilds_a_snapshot_for_a_record_without_a_digest(tmp_path: Path) -> None:
    """导入端没有源清单的内容事实可用：版本记录没有指纹、包里又缺快照时不补，登记按 stale 导入。"""
    pm, project_dir = _current_project(tmp_path)
    snapshot_rel = _selected_record(project_dir)["file"]
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")
    with zipfile.ZipFile(archive_path) as archive:
        versions = json.loads(archive.read("demo/versions/versions.json"))
    history = versions["videos"]["E1S1"]
    [record] = [item for item in history["versions"] if item["version"] == history["current_version"]]
    record.pop("content_digest")
    stripped = _rezip_with(
        archive_path,
        tmp_path / "no-digest.zip",
        {f"demo/{snapshot_rel}": None, "demo/versions/versions.json": json.dumps(versions).encode()},
    )

    target, result = _import_archive(stripped, tmp_path / "target")
    imported = target.get_project_path(result.project_name)

    assert not (imported / snapshot_rel).exists()
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


# ---- 第三轮：以 stale 导入的视频能重新生成、能切回版本，各自按真实依据重新登记 ----


def _stale_imported_video(tmp_path: Path) -> tuple[ProjectManager, str, Path]:
    pm, project_dir = _current_project(tmp_path)
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")
    first = _rezip_with(archive_path, tmp_path / "first.zip", {f"demo/{_selected_record(project_dir)['file']}": None})
    target, result = _import_archive(first, tmp_path / "hop1")
    imported = target.get_project_path(result.project_name)
    # 再经一次导出导入，登记带上占位依据
    _, again, twice = _round_trip(target, tmp_path / "hop2")
    entry = ProjectArtifactManifestAdapter(twice).snapshot_entries()[_VIDEO]
    assert entry.basis_digest == UNPROVEN_MEDIA_BASIS_DIGEST
    assert _status(twice, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE
    del imported
    return ProjectManager(tmp_path / "hop2"), again.project_name, twice


def test_a_carried_as_stale_video_registers_a_real_basis_when_regenerated(tmp_path: Path) -> None:
    _pm, _name, project = _stale_imported_video(tmp_path)
    record = _selected_record(project)
    staged = project / "videos" / ".scene_E1S1.new.mp4"
    staged.write_bytes(b"regenerated video")
    keys = (
        "execution_checkpoint_schema_version",
        "execution_duration_seconds",
        "execution_request_digest",
        "execution_script_file",
        "execution_provider_media",
        "execution_generate_audio",
        "artifact_video_currency",
    )

    outcome = commit_paid_video_artifact(
        project_path=project,
        versions=VersionManager(project),
        resource_type="videos",
        resource_id="E1S1",
        prompt="regenerated",
        staged_file=staged,
        current_file=project / _VIDEO_PATH,
        duration_seconds=record["execution_duration_seconds"],
        # 新生成的版本以当前选中的版本为父版本：生成任务就是这样记的，否则不会被选中
        version_metadata={
            **{key: record[key] for key in keys},
            "artifact_video_currency": dataclasses.replace(
                VideoArtifactCurrencyFacts.from_dict(record["artifact_video_currency"]),
                parent_version=record["version"],
            ).to_dict(),
        },
        resolve_current_basis=lambda metadata: (
            VideoArtifactCurrencyFacts.from_dict(metadata["artifact_video_currency"]).video_descriptor
        ),
    )

    assert outcome.selected is True
    entry = ProjectArtifactManifestAdapter(project).snapshot_entries()[_VIDEO]
    assert entry.basis_digest != UNPROVEN_MEDIA_BASIS_DIGEST
    assert _status(project, _VIDEO, _VIDEO_PATH) is ArtifactStatus.CURRENT


async def test_a_carried_as_stale_video_registers_a_real_basis_when_switched_back_to_its_version(
    tmp_path: Path,
) -> None:
    pm, name, project = _stale_imported_video(tmp_path)
    version = _selected_record(project)["version"]

    await restore_typed_media_resource(
        project_manager=pm,
        versions=VersionManager(project),
        project_name=name,
        resource_type="videos",
        resource_id="E1S1",
        version=version,
    )

    entry = ProjectArtifactManifestAdapter(project).snapshot_entries()[_VIDEO]
    assert entry.basis_digest != UNPROVEN_MEDIA_BASIS_DIGEST
    assert entry.content is not None
    assert _status(project, _VIDEO, _VIDEO_PATH) is ArtifactStatus.CURRENT


# ---- 第四轮 ----


def _set_segment(project_dir: Path, *path: str, value: object, index: int = 0) -> None:
    script_path = project_dir / "scripts" / "episode_1.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    holder = script["segments"][index]
    for part in path[:-1]:
        holder = holder[part]
    holder[path[-1]] = value
    script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")


def test_a_snapshot_path_that_is_a_directory_on_import_is_reported_and_imports_as_stale(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    snapshot_rel = _selected_record(project_dir)["file"]
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")
    with zipfile.ZipFile(archive_path) as source, zipfile.ZipFile(tmp_path / "dir.zip", "w") as rebuilt:
        for info in source.infolist():
            if info.filename == f"demo/{snapshot_rel}":
                rebuilt.writestr(f"demo/{snapshot_rel}/", b"")
                rebuilt.writestr(f"demo/{snapshot_rel}/inner", b"x")
            else:
                rebuilt.writestr(info, source.read(info))

    target, result = _import_archive(tmp_path / "dir.zip", tmp_path / "target")

    assert ("version_snapshot_not_a_file", snapshot_rel) in _noticed(result.diagnostics, "warnings")
    assert _status(target.get_project_path(result.project_name), _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


def test_a_backslash_reference_to_an_existing_file_is_normalised_and_not_lost(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    _set_segment(project_dir, "generated_assets", "storyboard_image", value="storyboards\\scene_E1S1.png")

    _, _, imported = _round_trip(pm, tmp_path / "target")

    script = json.loads((imported / "scripts" / "episode_1.json").read_text(encoding="utf-8"))
    assert script["segments"][0]["generated_assets"]["storyboard_image"] == _STORYBOARD_PATH
    assert _status(imported, _STORYBOARD, _STORYBOARD_PATH) is not ArtifactStatus.MISSING


def test_a_video_stale_because_of_a_dangling_input_stays_stale_after_the_reference_is_cleared(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    _set_segment(project_dir, "end_frame_image", value="end_frames/E1S1_end.png")
    assert _status(project_dir, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert ("claim_kept_stale_inputs_changed", _VIDEO_PATH) in _noticed(diagnostics, "warnings")
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE


def test_a_snapshot_path_shared_by_two_records_is_never_overwritten(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    versions = json.loads(_versions_path(project_dir).read_text(encoding="utf-8"))
    first = versions["videos"]["E1S1"]["versions"][0]
    second = versions["videos"]["E1S2"]["versions"][0]
    second["file"] = first["file"]
    _versions_path(project_dir).write_text(json.dumps(versions), encoding="utf-8")
    shared = (project_dir / first["file"]).read_bytes()
    second_video = ArtifactKey.episode_video(1, "E1S2")
    assert _status(project_dir, second_video, "videos/scene_E1S2.mp4") is ArtifactStatus.CURRENT

    diagnostics, _, imported = _round_trip(pm, tmp_path / "target")

    assert not [code for code, _ in _noticed(diagnostics, "auto_fixed") if code == "version_snapshot_restored"]
    assert (imported / first["file"]).read_bytes() == shared
    assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.CURRENT


def test_a_stale_import_is_announced_on_every_hop(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")
    first = _rezip_with(archive_path, tmp_path / "hop0.zip", {f"demo/{_selected_record(project_dir)['file']}": None})
    target, result = _import_archive(first, tmp_path / "hop1")
    assert ("claim_imported_as_stale", _VIDEO_PATH) in _noticed(result.diagnostics, "warnings")

    for hop in (2, 3):
        diagnostics, result, imported = _round_trip(target, tmp_path / f"hop{hop}")
        assert ("claim_carried_as_stale", _VIDEO_PATH) in _noticed(diagnostics, "warnings"), hop
        assert ("claim_imported_as_stale", _VIDEO_PATH) in _noticed(result.diagnostics, "warnings"), hop
        assert _status(imported, _VIDEO, _VIDEO_PATH) is ArtifactStatus.STALE
        target = ProjectManager(tmp_path / f"hop{hop}")


def test_a_healthy_round_trip_warns_about_nothing_stale(tmp_path: Path) -> None:
    pm, _project_dir = _current_project(tmp_path)

    diagnostics, result, _ = _round_trip(pm, tmp_path / "target")

    assert _noticed(diagnostics, "warnings") == []
    assert _noticed(result.diagnostics, "warnings") == []


def test_a_stale_video_whose_version_file_does_not_match_is_not_promised_a_switch_back(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)

    _target, result = _import_archive(_forged_archive(pm, tmp_path, project_dir), tmp_path / "target")

    warned = _noticed(result.diagnostics, "warnings")
    assert ("claim_imported_as_stale_unrestorable", _VIDEO_PATH) in warned
    assert ("claim_imported_as_stale", _VIDEO_PATH) not in warned


def test_a_reference_to_a_hidden_file_is_cleared_with_its_own_reason(tmp_path: Path) -> None:
    pm, project_dir = _current_project(tmp_path)
    (project_dir / ".style.png").write_bytes(b"png")
    project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    project["style_image"] = ".style.png"
    (project_dir / "project.json").write_text(json.dumps(project), encoding="utf-8")

    diagnostics, _, _ = _round_trip(pm, tmp_path / "target")

    assert ("hidden_reference_cleared", "project.json:project.style_image") in _noticed(diagnostics, "auto_fixed")


def test_claim_digest_rebuilds_only_the_selected_version(tmp_path: Path) -> None:
    """登记的内容事实只证明选中版本的字节：别的版本即使记录也没有指纹，也不拿它补。"""
    pm, project_dir = _current_project(tmp_path)
    drop_selected_version_snapshot(project_dir, "videos", "E1S1")
    versions = json.loads(_versions_path(project_dir).read_text(encoding="utf-8"))
    history = versions["videos"]["E1S1"]
    [selected] = history["versions"]
    selected.pop("content_digest")
    other = {**selected, "version": 2, "file": selected["file"].replace("_v1_", "_v2_")}
    history["versions"].append(other)
    _versions_path(project_dir).write_text(json.dumps(versions), encoding="utf-8")
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert f"demo/{selected['file']}" in names
    assert f"demo/{other['file']}" not in names


def test_a_reference_outside_its_confined_folder_is_reported_not_cleared(tmp_path: Path) -> None:
    """只清引用的文件不在的引用；其他引用错误（如尾帧指向 end_frames 之外）照常由导入校验报出。"""
    pm, project_dir = _current_project(tmp_path)
    _set_segment(project_dir, "end_frame_image", value=_STORYBOARD_PATH)

    diagnostics = ProjectArchiveService(pm).get_export_diagnostics("demo", scope="full")

    assert not [code for code, _ in _noticed(diagnostics, "auto_fixed") if "reference_cleared" in code]
    assert diagnostics["blocking"]


def test_import_refuses_an_archive_with_duplicate_entry_names(tmp_path: Path) -> None:
    pm, _project_dir = _current_project(tmp_path)
    archive_path, _ = ProjectArchiveService(pm).export_project("demo", scope="full")
    duplicated = tmp_path / "dup.zip"
    with zipfile.ZipFile(archive_path) as source, zipfile.ZipFile(duplicated, "w") as rebuilt:
        for info in source.infolist():
            rebuilt.writestr(info, source.read(info))
        with pytest.warns(UserWarning, match="Duplicate name"):
            rebuilt.writestr(f"demo/{_VIDEO_PATH}", b"second copy")

    with pytest.raises(ProjectArchiveValidationError) as exc:
        ProjectArchiveService(ProjectManager(tmp_path / "target")).import_project_archive(
            duplicated, uploaded_filename="demo.zip"
        )

    assert exc.value.status_code == 400
    assert [message.key for message in exc.value.errors] == ["arch_zip_duplicate_entry"]
