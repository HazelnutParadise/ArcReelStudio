"""schema 19 的项目带着过去正常流程写出的旧形态：链首规整后升到当前版本，原内容留在盘上，报告列出改动（ADR 0098）。

单件损坏（读不出的宫格记录或草稿）不拒绝整个项目：导入激活原样留下并进报告。样本取自 ``tests/legacy_project_shapes.py``，
形态清单见 ``docs/agents/project-migrations.md``「已知旧形态」。
"""

from __future__ import annotations

import json
import os
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from lib.artifacts.artifact_currency import ArtifactCurrencyResolver
from lib.artifacts.artifact_manifest import (
    MANIFEST_FILENAME,
    ArtifactBasis,
    ArtifactKey,
    ArtifactManifest,
    ProjectArtifactManifestAdapter,
)
from lib.project.asset_derivatives import derivative_artifact_key
from lib.project.project_manager import ProjectManager
from lib.project.project_migration_failure import ProjectMigrationError
from lib.project.project_migration_report import (
    MigrationReport,
    acknowledge_migration_report,
    load_migration_report,
    visible_migration_report,
)
from lib.project.project_migrations import legacy_shapes, runner
from lib.project.project_migrations.legacy_shapes import normalize_legacy_shapes
from lib.project.project_migrations.runner import migrate_project_with_verdict
from lib.project.project_schema import CURRENT_PROJECT_SCHEMA_VERSION
from lib.project.resource_paths import (
    CHARACTER_DERIVATIVE_RESOURCE_TYPE,
    END_FRAME_RESOURCE_TYPE,
    resource_relative_path,
)
from lib.script.script_review import content_fingerprint
from lib.workflow.workflow_state import WorkflowStateService
from server.services.project.project_archive import ProjectArchiveService, ProjectArchiveValidationError
from tests.factories import wrap_the_last_migration_step
from tests.legacy_project_shapes import (
    SCHEMA_V19,
    activate_at_schema_19,
    add_asset_names_differing_only_in_case,
    add_colliding_asset_name,
    break_script_item_ids,
    refer_to_asset_in_episode,
    repoint_registered_asset_sheet,
    reuse_item_id_across_episodes,
    set_script_episode,
    share_asset_sheets,
    share_derivative_sheet,
    share_reference_files,
    write_legacy_shared_reference_project,
    write_legacy_tts_narration_project,
    write_unreadable_grid_record,
    write_unreadable_script_plan_draft,
    write_v19_project,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _project(root: Path, *, activate: bool = True) -> Path:
    """``root/projects/demo``：:func:`write_v19_project` 的解说分镜样本。"""
    return write_v19_project(root / "projects", activate=activate)


def _register_test_claim(project_dir: Path, key: ArtifactKey, artifact_path: str) -> None:
    ArtifactManifest(ProjectArtifactManifestAdapter(project_dir)).register(
        key,
        artifact_path=artifact_path,
        basis=ArtifactBasis.build("test/claim", kind_version=1, inputs={"path": artifact_path}),
    )


def _migrate(project_dir: Path) -> None:
    assert migrate_project_with_verdict(project_dir) is None
    assert _read_json(project_dir / "project.json")["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION


def _adjusted(project_dir: Path) -> list[tuple[str, int | None, dict[str, str]]]:
    report = load_migration_report(project_dir)
    assert report is not None
    assert report.complete
    return [(item.code, item.episode, item.params) for item in report.adjusted]


def test_a_script_without_its_episode_number_takes_the_one_it_is_bound_to(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    set_script_episode(project_dir, 1, None)

    _migrate(project_dir)

    assert _read_json(project_dir / "scripts" / "episode_1.json")["episode"] == 1
    assert _adjusted(project_dir) == [("script_episode_corrected", 1, {"from": "", "to": "1"})]


def test_asset_names_that_collide_after_normalization_keep_the_first(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    colliding = add_colliding_asset_name(project_dir, "characters", "阿离")

    _migrate(project_dir)

    assert list(_read_json(project_dir / "project.json")["characters"]) == ["阿离"]
    assert _adjusted(project_dir) == [
        ("duplicate_asset_removed", None, {"asset_type": "character", "name": colliding, "kept": "阿离"})
    ]
    report = load_migration_report(project_dir)
    assert report is not None
    assert report.adjusted[0].backup is not None
    assert colliding in _read_json(project_dir / report.adjusted[0].backup)["characters"]


def test_asset_names_that_differ_only_in_case_keep_the_first(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    variant = add_asset_names_differing_only_in_case(project_dir, "props", "prop_sheet", "Umbrella")
    # 清单按不区分大小写的路径判重，两条只差大小写的资产图只能有一条登记。
    _register_test_claim(project_dir, ArtifactKey.asset_sheet("prop", "Umbrella"), "props/Umbrella.png")

    _migrate(project_dir)

    assert list(_read_json(project_dir / "project.json")["props"]) == ["伞", "Umbrella"]
    assert _adjusted(project_dir) == [
        ("duplicate_asset_removed", None, {"asset_type": "prop", "name": variant, "kept": "Umbrella"})
    ]
    report = load_migration_report(project_dir)
    assert report is not None
    assert report.adjusted[0].backup is not None
    assert variant in _read_json(project_dir / report.adjusted[0].backup)["props"]
    entries = ProjectArtifactManifestAdapter(project_dir).snapshot_entries()
    assert ArtifactKey.asset_sheet("prop", "Umbrella") in entries
    assert ArtifactKey.asset_sheet("prop", variant) not in entries


_SHARED_REFERENCE_COPIES = [
    (
        "characters/refs/阿青.png",
        {"asset_type": "character", "name": "阿青", "owner": "阿离", "from": "characters/refs/阿离.png"},
    ),
    (
        "characters/refs_audio/阿青.wav",
        {"asset_type": "character", "name": "阿青", "owner": "阿离", "from": "characters/refs_audio/阿离.wav"},
    ),
    (
        "products/refs/茶_1.png",
        {"asset_type": "product", "name": "茶", "owner": "咖啡", "from": "products/refs/咖啡_1.png"},
    ),
]


def _copied_reference_files(project_dir: Path) -> list[tuple[str | None, dict[str, str]]]:
    report = load_migration_report(project_dir)
    assert report is not None
    return [(item.file, item.params) for item in report.adjusted if item.code == "shared_reference_file_copied"]


@pytest.mark.parametrize("fail_commit", [False, True])
def test_swapped_shared_references_keep_each_original_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_commit: bool
) -> None:
    project_dir = write_legacy_shared_reference_project(ProjectManager(tmp_path).projects_dir)
    project_path = project_dir / "project.json"
    project = _read_json(project_path)
    project["characters"]["Alice"]["reference_image"] = "characters/refs/Bob.png"
    project["products"] = {}
    project_path.write_text(json.dumps(project), encoding="utf-8")
    (project_dir / "characters/refs/Bob.png").write_bytes(b"bob-image")
    write = legacy_shapes.atomic_write_json

    def fail_on_project(path: Path, payload: Any) -> None:
        if path.name == "project.json":
            raise OSError("disk full")
        write(path, payload)

    if fail_commit:
        with monkeypatch.context() as patch:
            patch.setattr(legacy_shapes, "atomic_write_json", fail_on_project)
            with pytest.raises(OSError, match="disk full"):
                runner.migrate_project_dir(project_dir)

    _migrate(project_dir)

    migrated = _read_json(project_path)
    for name, expected in (("Alice", b"bob-image"), ("Bob", b"image")):
        assert migrated["characters"][name]["reference_image"] == f"characters/refs/{name}.png"
        assert (project_dir / f"characters/refs/{name}.png").read_bytes() == expected


def test_shared_reference_copy_failure_keeps_the_displaced_original_in_the_retry_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = write_legacy_shared_reference_project(ProjectManager(tmp_path).projects_dir)
    target = project_dir / "characters/refs/Bob.png"
    target.write_bytes(b"displaced-original")
    write = legacy_shapes.atomic_write_bytes

    def disk_full_on_copy(path: Path, content: bytes) -> None:
        if path == target:
            raise OSError("disk full")
        write(path, content)

    with monkeypatch.context() as patch:
        patch.setattr(legacy_shapes, "atomic_write_bytes", disk_full_on_copy)
        with pytest.raises(OSError, match="disk full"):
            runner.migrate_project_dir(project_dir)
    _migrate(project_dir)

    report = load_migration_report(project_dir)
    assert report is not None
    [copied] = [item for item in report.adjusted if item.file == "characters/refs/Bob.png"]
    assert copied.backup is not None
    assert (project_dir / copied.backup).read_bytes() == b"displaced-original"
    assert target.read_bytes() == b"image"
    assert len(list(target.parent.glob("Bob.png.kept.*"))) == 1


def test_reference_files_shared_with_another_asset_get_their_own_copy(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    contents = share_reference_files(project_dir)

    _migrate(project_dir)

    project = _read_json(project_dir / "project.json")
    qing, ali = project["characters"]["阿青"], project["characters"]["阿离"]
    assert (qing["reference_image"], qing["reference_audio"]) == (
        "characters/refs/阿青.png",
        "characters/refs_audio/阿青.wav",
    )
    assert (ali["reference_image"], ali["reference_audio"]) == (
        "characters/refs/阿离.png",
        "characters/refs_audio/阿离.wav",
    )
    assert project["products"]["茶"]["reference_images"] == ["products/refs/茶_1.png"]
    assert project["products"]["咖啡"]["reference_images"] == ["products/refs/咖啡_1.png"]
    copies = {"characters/refs/阿青.png": "characters/refs/阿离.png"} | {
        target: params["from"] for target, params in _SHARED_REFERENCE_COPIES
    }
    for target, source in copies.items():
        assert (project_dir / target).read_bytes() == contents[source]
        assert (project_dir / source).read_bytes() == contents[source]
    assert _copied_reference_files(project_dir) == _SHARED_REFERENCE_COPIES
    report = load_migration_report(project_dir)
    assert report is not None
    [stray_backup] = [item.backup for item in report.adjusted if item.backup is not None]
    assert (project_dir / stray_backup).read_bytes() == b"qing-stray"
    shown = WorkflowStateService(ProjectManager(str(tmp_path))).get_status("demo").migration_report
    assert shown is not None
    assert [item.code for item in shown.adjusted] == ["shared_reference_file_copied"] * 3


@pytest.mark.parametrize("resolved_project_dir", [False, True])
def test_a_reference_spelled_differently_still_gets_its_own_copy(tmp_path: Path, resolved_project_dir: bool) -> None:
    # 旧版 PATCH 原样收下任意字符串：带 ``..`` / ``.`` 段、反斜杠或项目内绝对路径，运行时照样读到别的资产名下的文件。
    project_dir = _project(tmp_path)
    contents = share_reference_files(project_dir)
    project = _read_json(project_dir / "project.json")
    base = Path(os.path.realpath(project_dir)) if resolved_project_dir else project_dir
    project["characters"]["阿青"]["reference_image"] = "characters/./refs/阿离.png"
    project["characters"]["阿青"]["reference_audio"] = (
        base / "characters/refs_audio/../refs_audio/阿离.wav"
    ).as_posix()
    project["products"]["茶"]["reference_images"] = ["products\\refs\\..\\refs\\咖啡_1.png"]
    (project_dir / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")

    _migrate(project_dir)

    project = _read_json(project_dir / "project.json")
    qing = project["characters"]["阿青"]
    assert (qing["reference_image"], qing["reference_audio"]) == (
        "characters/refs/阿青.png",
        "characters/refs_audio/阿青.wav",
    )
    assert project["products"]["茶"]["reference_images"] == ["products/refs/茶_1.png"]
    assert (project_dir / qing["reference_image"]).read_bytes() == contents["characters/refs/阿离.png"]
    assert (project_dir / qing["reference_audio"]).read_bytes() == contents["characters/refs_audio/阿离.wav"]
    assert (project_dir / "products/refs/茶_1.png").read_bytes() == contents["products/refs/咖啡_1.png"]
    assert [params["from"] for _, params in _copied_reference_files(project_dir)] == [
        "characters/refs/阿离.png",
        "characters/refs_audio/阿离.wav",
        "products/refs/咖啡_1.png",
    ]


@pytest.mark.parametrize("sample", ["shared-references", "shared-with-a-sibling"])
def test_an_asset_name_with_path_separators_gets_no_copy_outside_its_directory(tmp_path: Path, sample: str) -> None:
    # 导入包在校验资产名之前跑迁移链：名字里的 ``..`` 段不能把共用参考文件的副本带出项目目录。
    if sample == "shared-references":
        project_dir = write_legacy_shared_reference_project(ProjectManager(tmp_path).projects_dir)
        image, audio = "characters/refs/Alice.png", "characters/refs_audio/Alice.wav"
    else:
        project_dir = _project(tmp_path)
        share_reference_files(project_dir)
        image, audio = "characters/refs/阿离.png", "characters/refs_audio/阿离.wav"
    project = _read_json(project_dir / "project.json")
    escaping = {"description": "escaping", "reference_image": image, "reference_audio": audio, "character_sheet": image}
    project["characters"]["../../../../escaped"] = escaping
    (project_dir / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")

    migrate_project_with_verdict(project_dir)

    assert list(tmp_path.rglob("escaped*")) == []
    entry = _read_json(project_dir / "project.json")["characters"]["../../../../escaped"]
    assert (entry["reference_image"], entry["reference_audio"], entry["character_sheet"]) == (image, audio, image)


def test_copying_shared_reference_files_converges_after_a_failed_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = _project(tmp_path)
    share_reference_files(project_dir)
    record: list[Any] = []
    write = legacy_shapes.atomic_write_json

    def fail_on_project(path: Path, payload: Any) -> None:
        if path.name == "project.json":
            raise OSError("disk full")
        write(path, payload)

    # 副本都已落盘、保留副本也已挪出，改指的 project.json 提交失败。
    with monkeypatch.context() as patch:
        patch.setattr(legacy_shapes, "atomic_write_json", fail_on_project)
        with pytest.raises(OSError, match="disk full"):
            normalize_legacy_shapes(project_dir, schema_version=SCHEMA_V19, record=record)
    normalize_legacy_shapes(project_dir, schema_version=SCHEMA_V19, record=record)

    assert [(item.file, item.params) for item in record] == _SHARED_REFERENCE_COPIES
    assert record[0].backup is not None
    assert (project_dir / record[0].backup).read_bytes() == b"qing-stray"
    assert _read_json(project_dir / "project.json")["products"]["茶"]["reference_images"] == ["products/refs/茶_1.png"]
    assert not (project_dir / "products" / "refs" / "茶_2.png").exists()
    assert len(list((project_dir / "characters" / "refs").glob("阿青.png.kept.*"))) == 1


def _sheet_claim(project_dir: Path, asset_type: str, name: str) -> tuple[str, str] | None:
    entry = ProjectArtifactManifestAdapter(project_dir).get_entry(ArtifactKey.asset_sheet(asset_type, name))
    return None if entry is None else (entry.artifact_path, entry.basis_digest)


def _sheet_status(project_dir: Path, asset_type: str, name: str, rel: str) -> str:
    comparison = ArtifactCurrencyResolver(project_dir).compare(
        ArtifactKey.asset_sheet(asset_type, name), artifact_path=rel
    )
    return comparison.status.value


def _project_sharing_sheets(tmp_path: Path) -> tuple[Path, dict[str, bytes], str]:
    """「阿青」在清单激活前共用「阿离」的参考图作资产图，激活后「雨巷」又改指「伞」的资产图。

    返回样本、各图改指前的内容与「阿青」按共用路径登记的依据摘要。
    """
    project_dir = _project(tmp_path, activate=False)
    contents = share_asset_sheets(project_dir)
    activate_at_schema_19(project_dir)
    claim = _sheet_claim(project_dir, "character", "阿青")
    assert claim is not None
    assert claim[0] == "characters/refs/阿离.png"
    scene_claim = _sheet_claim(project_dir, "scene", "雨巷")
    assert scene_claim is not None
    assert scene_claim[0] == "scenes/雨巷.png"
    contents |= repoint_registered_asset_sheet(project_dir)
    return project_dir, contents, claim[1]


def _assert_sheets_keep_their_currency(
    tmp_path: Path, project_dir: Path, contents: dict[str, bytes], qing_digest: str
) -> None:
    project = _read_json(project_dir / "project.json")
    assert project["characters"]["阿青"]["character_sheet"] == "characters/阿青.png"
    assert project["scenes"]["雨巷"]["scene_sheet"] == "scenes/雨巷.png"
    assert project["characters"]["阿离"]["reference_image"] == "characters/refs/阿离.png"
    assert project["props"]["伞"]["prop_sheet"] == "props/伞.png"
    assert (project_dir / "characters/阿青.png").read_bytes() == contents["characters/refs/阿离.png"]
    assert (project_dir / "scenes/雨巷.png").read_bytes() == contents["props/伞.png"]
    assert (project_dir / "characters/refs/阿离.png").read_bytes() == contents["characters/refs/阿离.png"]
    assert (project_dir / "props/伞.png").read_bytes() == contents["props/伞.png"]
    # 登记在共用路径上的随改指换到副本，依据摘要不变：副本与原文件同字节，仍读作时新。
    assert _sheet_claim(project_dir, "character", "阿青") == ("characters/阿青.png", qing_digest)
    assert _sheet_status(project_dir, "character", "阿青", "characters/阿青.png") == "current"
    # 「雨巷」原有的登记描述的是被挪成保留副本的那张图：撤掉，改指前后都读作缺失，不借副本伪造成时新。
    assert _sheet_claim(project_dir, "scene", "雨巷") is None
    assert _sheet_status(project_dir, "scene", "雨巷", "scenes/雨巷.png") == "missing"
    sheets = WorkflowStateService(ProjectManager(str(tmp_path))).get_status("demo").artifacts["asset_sheets"]
    assert "阿青" in sheets["character"]["current_ids"]
    assert "雨巷" in sheets["scene"]["missing_ids"]


def test_an_asset_sheet_shared_with_another_asset_gets_its_own_copy_and_keeps_its_currency(tmp_path: Path) -> None:
    project_dir, contents, qing_digest = _project_sharing_sheets(tmp_path)

    _migrate(project_dir)

    _assert_sheets_keep_their_currency(tmp_path, project_dir, contents, qing_digest)
    copied = _copied_reference_files(project_dir)
    assert copied == [
        (
            "characters/阿青.png",
            {"asset_type": "character", "name": "阿青", "owner": "阿离", "from": "characters/refs/阿离.png"},
        ),
        ("scenes/雨巷.png", {"asset_type": "scene", "name": "雨巷", "owner": "伞", "from": "props/伞.png"}),
    ]
    report = load_migration_report(project_dir)
    assert report is not None
    backups = {item.file: item.backup for item in report.adjusted if item.code == "shared_reference_file_copied"}
    assert (project_dir / str(backups["characters/阿青.png"])).read_bytes() == b"qing-stray"
    assert (project_dir / str(backups["scenes/雨巷.png"])).read_bytes() == contents["scenes/雨巷.png"]


def test_a_failed_sheet_copy_commit_rolls_the_claims_back_and_the_retry_converges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir, contents, qing_digest = _project_sharing_sheets(tmp_path)
    manifest = (project_dir / MANIFEST_FILENAME).read_bytes()
    project = (project_dir / "project.json").read_bytes()
    write = legacy_shapes.atomic_write_json

    def fail_on_project(path: Path, payload: Any) -> None:
        if path.name == "project.json":
            raise OSError("disk full")
        write(path, payload)

    with monkeypatch.context() as patch:
        patch.setattr(legacy_shapes, "atomic_write_json", fail_on_project)
        with pytest.raises(OSError, match="disk full"):
            runner.migrate_project_dir(project_dir)

    # 改指没能提交：复制落点、登记与 project.json 一并回到改前。
    assert (project_dir / "characters/阿青.png").read_bytes() == b"qing-stray"
    assert (project_dir / "scenes/雨巷.png").read_bytes() == contents["scenes/雨巷.png"]
    assert (project_dir / MANIFEST_FILENAME).read_bytes() == manifest
    assert (project_dir / "project.json").read_bytes() == project

    _migrate(project_dir)

    _assert_sheets_keep_their_currency(tmp_path, project_dir, contents, qing_digest)
    assert len(list((project_dir / "characters").glob("阿青.png.kept.*"))) == 1
    assert len(list((project_dir / "scenes").glob("雨巷.png.kept.*"))) == 1


def test_a_body_sheet_pointing_at_another_assets_derivative_gets_its_own_copy(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    project_path = project_dir / "project.json"
    derivative = share_derivative_sheet(project_dir)

    _migrate(project_dir)

    characters = _read_json(project_path)["characters"]
    assert characters["阿青"]["character_sheet"] == "characters/阿青.png"
    assert (project_dir / "characters/阿青.png").read_bytes() == b"raincoat"
    assert (project_dir / derivative).read_bytes() == b"raincoat"
    assert _sheet_status(project_dir, "character", "阿青", "characters/阿青.png") == "missing"


@pytest.mark.parametrize("source_link", ["file", "parent"])
def test_an_unsafe_shared_sheet_source_is_not_copied_into_a_current_claim(tmp_path: Path, source_link: str) -> None:
    project_dir, _, _ = _project_sharing_sheets(tmp_path)
    source = project_dir / "characters/refs/阿离.png"
    if source_link == "file":
        real = source.with_name("real.png")
        source.rename(real)
        source.symlink_to(real)
    else:
        directory = source.parent
        real = directory.with_name("real-refs")
        directory.rename(real)
        directory.symlink_to(real, target_is_directory=True)
    claim = _sheet_claim(project_dir, "character", "阿青")

    runner.migrate_project_dir(project_dir)

    assert (
        _read_json(project_dir / "project.json")["characters"]["阿青"]["character_sheet"] == "characters/refs/阿离.png"
    )
    assert (project_dir / "characters/阿青.png").read_bytes() == b"qing-stray"
    assert _sheet_status(project_dir, "character", "阿青", "characters/阿青.png") != "current"
    assert _sheet_claim(project_dir, "character", "阿青") == claim
    observed = ArtifactManifest(ProjectArtifactManifestAdapter(project_dir)).compare_entry(
        ArtifactKey.asset_sheet("character", "阿青"), artifact_path="characters/refs/阿离.png", expected=None
    )
    assert observed.status.value == "blocked"
    assert observed.blocker is not None
    assert observed.blocker.code == "artifact_symlink"


@pytest.mark.parametrize("external_bytes", [b"ali-image", b"other", None])
def test_a_sheet_copy_replaces_the_destination_symlink_without_touching_its_target(
    tmp_path: Path, external_bytes: bytes | None
) -> None:
    project_dir, contents, digest = _project_sharing_sheets(tmp_path)
    external = tmp_path / "external.png"
    if external_bytes is not None:
        external.write_bytes(external_bytes)
    target = project_dir / "characters/阿青.png"
    target.unlink()
    target.symlink_to(external)

    _migrate(project_dir)

    assert not target.is_symlink()
    _assert_sheets_keep_their_currency(tmp_path, project_dir, contents, digest)
    if external_bytes is not None:
        assert external.read_bytes() == external_bytes
    else:
        assert not external.exists()


def test_a_sheet_copy_does_not_write_through_a_symlink_directory(tmp_path: Path) -> None:
    manager = ProjectManager(tmp_path / "data")
    manager.create_project("demo")
    project_dir = manager.get_project_path("demo")
    project_path = project_dir / "project.json"
    project = _read_json(project_path)
    project["schema_version"] = SCHEMA_V19
    project["characters"] = {"Bob": {"description": "Bob", "character_sheet": "props/Umbrella.png"}}
    project["props"] = {"Umbrella": {"description": "Umbrella", "prop_sheet": "props/Umbrella.png"}}
    project_path.write_text(json.dumps(project), encoding="utf-8")
    (project_dir / "props/Umbrella.png").write_bytes(b"source")
    outside = tmp_path / "outside"
    (project_dir / "characters").rename(outside)
    (project_dir / "characters").symlink_to(outside, target_is_directory=True)
    original = project_path.read_bytes()

    with pytest.raises(ValueError, match="copy directory is a symlink"):
        runner.migrate_project_dir(project_dir)

    assert not (outside / "Bob.png").exists()
    assert project_path.read_bytes() == original


@pytest.mark.parametrize(
    "spelling", ["./characters/refs/阿离.png", "characters/refs/../refs/阿离.png", "characters\\refs\\阿离.png"]
)
def test_a_shared_sheet_with_a_noncanonical_spelling_gets_a_safe_copy(tmp_path: Path, spelling: str) -> None:
    project_dir, _, _ = _project_sharing_sheets(tmp_path)
    project_path = project_dir / "project.json"
    project = _read_json(project_path)
    project["characters"]["阿青"]["character_sheet"] = spelling
    project_path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")

    _migrate(project_dir)

    assert _read_json(project_path)["characters"]["阿青"]["character_sheet"] == "characters/阿青.png"
    assert (project_dir / "characters/阿青.png").read_bytes() == b"ali-image"
    assert _sheet_status(project_dir, "character", "阿青", "characters/阿青.png") == "missing"


def test_bidirectional_sheet_sharing_copies_the_original_bytes(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    project_path = project_dir / "project.json"
    project = _read_json(project_path)
    project["characters"]["阿离"]["character_sheet"] = "characters/阿青.png"
    project["characters"]["阿青"] = {"description": "青衣少年", "character_sheet": "characters/阿离.png"}
    project_path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    original = (project_dir / "characters/阿离.png").read_bytes()
    (project_dir / "characters/阿青.png").write_bytes(b"qing")

    _migrate(project_dir)

    characters = _read_json(project_path)["characters"]
    assert characters["阿离"]["character_sheet"] == "characters/阿离.png"
    assert characters["阿青"]["character_sheet"] == "characters/阿青.png"
    assert (project_dir / "characters/阿离.png").read_bytes() == b"qing"
    assert (project_dir / "characters/阿青.png").read_bytes() == original
    assert _sheet_status(project_dir, "character", "阿离", "characters/阿离.png") == "missing"


def test_bidirectional_sheet_sharing_with_crossed_claims_carries_both_claims(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    project_path = project_dir / "project.json"
    project = _read_json(project_path)
    project["characters"]["阿离"]["character_sheet"] = "characters/阿青.png"
    project["characters"]["阿青"] = {"description": "青衣少年", "character_sheet": "characters/阿离.png"}
    project_path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    ali_bytes = (project_dir / "characters/阿离.png").read_bytes()
    (project_dir / "characters/阿青.png").write_bytes(b"qing")
    # 两张图的登记都在各自共用的路径上：逐条改指时，第一条会落到另一条尚未换走的路径上。
    adapter = ProjectArtifactManifestAdapter(project_dir)
    ali_key = ArtifactKey.asset_sheet("character", "阿离")
    qing_key = ArtifactKey.asset_sheet("character", "阿青")
    ali_claim = adapter.get_entry(ali_key)
    assert ali_claim is not None
    qing_digest = "sha256-v1:" + "0" * 64
    crossed = {
        ali_key: replace(ali_claim, artifact_path="characters/阿青.png"),
        qing_key: replace(ali_claim, artifact_path="characters/阿离.png", basis_digest=qing_digest),
    }
    assert adapter.replace_entries_if_matches_atomically(expected={ali_key: ali_claim}, replacements=crossed)

    _migrate(project_dir)

    characters = _read_json(project_path)["characters"]
    assert characters["阿离"]["character_sheet"] == "characters/阿离.png"
    assert characters["阿青"]["character_sheet"] == "characters/阿青.png"
    assert (project_dir / "characters/阿离.png").read_bytes() == b"qing"
    assert (project_dir / "characters/阿青.png").read_bytes() == ali_bytes
    assert _sheet_claim(project_dir, "character", "阿离") == ("characters/阿离.png", ali_claim.basis_digest)
    assert _sheet_claim(project_dir, "character", "阿青") == ("characters/阿青.png", qing_digest)


def test_a_copied_sheet_keeps_its_stale_claim(tmp_path: Path) -> None:
    project_dir, _, digest = _project_sharing_sheets(tmp_path)
    project_path = project_dir / "project.json"
    project = _read_json(project_path)
    project["characters"]["阿青"]["description"] = "改变了描述"
    project_path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")

    _migrate(project_dir)

    assert _sheet_claim(project_dir, "character", "阿青") == ("characters/阿青.png", digest)
    assert _sheet_status(project_dir, "character", "阿青", "characters/阿青.png") == "stale"


def _issue_codes(tmp_path: Path) -> set[str]:
    status = WorkflowStateService(ProjectManager(str(tmp_path))).get_status("demo")
    return {issue.code for issue in status.issues}


def test_references_to_a_dropped_case_variant_follow_the_kept_name(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    variant = add_asset_names_differing_only_in_case(project_dir, "characters", "character_sheet", "Alice")
    refer_to_asset_in_episode(project_dir, 1, "characters_in_segment", variant)

    _migrate(project_dir)

    [segment] = _read_json(project_dir / "scripts" / "episode_1.json")["segments"]
    assert segment["characters_in_segment"] == ["Alice"]
    assert segment["image_prompt"] == "@[Alice]阿离站在雨中"
    draft = _read_json(project_dir / "drafts" / "episode_1" / "script_plan_segments.json")
    assert draft["segments"][0]["characters_in_segment"] == ["Alice"]
    assert _adjusted(project_dir) == [
        ("duplicate_asset_removed", None, {"asset_type": "character", "name": variant, "kept": "Alice"}),
        ("duplicate_asset_references_rewritten", 1, {"asset_type": "character", "name": variant, "kept": "Alice"}),
    ]
    assert "invalid_script_structure" not in _issue_codes(tmp_path)


def test_dialogue_speakers_and_unit_text_mentions_follow_the_kept_name(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "project.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_V19,
                "characters": {"Alice": {"description": "保留"}, "ALICE": {"description": "变体"}},
                "episodes": [
                    {"episode": 1, "script_file": "scripts/episode_1.json"},
                    {"episode": 2, "script_file": "scripts/episode_2.json"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (project_dir / "scripts").mkdir()
    (project_dir / "scripts" / "episode_1.json").write_text(
        json.dumps(
            {
                "episode": 1,
                "video_units": [{"unit_id": "E1U1", "text": "@[ALICE]：{你好}\n@[ALICE]推门，@[Alice]回头"}],
            }
        ),
        encoding="utf-8",
    )
    (project_dir / "scripts" / "episode_2.json").write_text(
        json.dumps(
            {
                "episode": 2,
                "scenes": [
                    {
                        "scene_id": "E2S01",
                        "characters_in_scene": ["ALICE", "Alice"],
                        "dialogue": [{"speaker": "ALICE", "line": "走吧"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    record: list = []

    normalize_legacy_shapes(project_dir, schema_version=SCHEMA_V19, record=record)

    [unit] = _read_json(project_dir / "scripts" / "episode_1.json")["video_units"]
    assert unit["text"] == "@[Alice]：{你好}\n@[Alice]推门，@[Alice]回头"
    [scene] = _read_json(project_dir / "scripts" / "episode_2.json")["scenes"]
    # 改写后与保留名重复的引用只留一个。
    assert scene["characters_in_scene"] == ["Alice"]
    assert scene["dialogue"] == [{"speaker": "Alice", "line": "走吧"}]
    assert [(item.code, item.episode) for item in record] == [
        ("duplicate_asset_removed", None),
        ("duplicate_asset_references_rewritten", 1),
        ("duplicate_asset_references_rewritten", 2),
    ]


def test_references_rewritten_before_a_failed_write_stay_in_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "project.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_V19,
                "characters": {"Alice": {"description": "保留"}, "ALICE": {"description": "变体"}},
                "episodes": [
                    {"episode": episode, "script_file": f"scripts/episode_{episode}.json"} for episode in (1, 2)
                ],
            }
        ),
        encoding="utf-8",
    )
    (project_dir / "scripts").mkdir()
    for episode in (1, 2):
        (project_dir / "scripts" / f"episode_{episode}.json").write_text(
            json.dumps(
                {"episode": episode, "segments": [{"segment_id": f"E{episode}S01", "characters_in_segment": ["ALICE"]}]}
            ),
            encoding="utf-8",
        )
    record: list = []
    write = legacy_shapes.atomic_write_json

    def fail_on_second_episode(path: Path, payload: Any) -> None:
        if path.name == "episode_2.json":
            raise OSError("disk full")
        write(path, payload)

    # 第 1 集已改写落盘、第 2 集写盘失败：重跑发现不了第 1 集的改写，报告要靠失败时的记录带到重试。
    with monkeypatch.context() as patch:
        patch.setattr(legacy_shapes, "atomic_write_json", fail_on_second_episode)
        with pytest.raises(OSError, match="disk full"):
            normalize_legacy_shapes(project_dir, schema_version=SCHEMA_V19, record=record)
    normalize_legacy_shapes(project_dir, schema_version=SCHEMA_V19, record=record)

    assert sorted((item.code, item.episode or 0) for item in record) == [
        ("duplicate_asset_references_rewritten", 1),
        ("duplicate_asset_references_rewritten", 2),
        ("duplicate_asset_removed", 0),
    ]


def _add_character_derivatives(project_dir: Path, owner: str, derivatives: dict[str, dict[str, str]]) -> None:
    project = _read_json(project_dir / "project.json")
    project["characters"][owner]["derivatives"] = derivatives
    (project_dir / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")


def test_derivatives_of_a_dropped_case_variant_join_the_kept_name(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    variant = add_asset_names_differing_only_in_case(project_dir, "characters", "character_sheet", "Alice")
    hat_sheet, coat_sheet = "characters/derivatives/ALICE/Hat.png", "characters/derivatives/ALICE/Coat.png"
    (project_dir / hat_sheet).parent.mkdir(parents=True)
    (project_dir / hat_sheet).write_bytes(b"hat")
    (project_dir / coat_sheet).write_bytes(b"coat")
    _add_character_derivatives(project_dir, "Alice", {"coat": {"description": "保留方的外套", "character_sheet": ""}})
    _add_character_derivatives(
        project_dir,
        variant,
        {
            "Coat": {"description": "变体的外套", "character_sheet": coat_sheet},
            "Hat": {"description": "帽子", "character_sheet": hat_sheet},
        },
    )
    hat_key, coat_key = derivative_artifact_key(variant, "Hat"), derivative_artifact_key(variant, "Coat")
    for key, sheet in ((hat_key, hat_sheet), (coat_key, coat_sheet)):
        ArtifactManifest(ProjectArtifactManifestAdapter(project_dir)).register(
            key,
            artifact_path=sheet,
            basis=ArtifactBasis.build("test/derivative-sheet", kind_version=1, inputs={"sheet": sheet}),
        )
    hat_claim = ProjectArtifactManifestAdapter(project_dir).get_entry(hat_key)
    versions_path = project_dir / "versions" / "versions.json"
    versions = _read_json(versions_path) if versions_path.is_file() else {}
    hat_history = {
        "current_version": 1,
        "versions": [
            {
                "version": 1,
                "file": "versions/character_derivatives/ALICE/Hat_v1_20260302T145652.png",
                "prompt": "帽子",
                "created_at": "2026-03-02T14:56:52Z",
            }
        ],
    }
    versions.setdefault(CHARACTER_DERIVATIVE_RESOURCE_TYPE, {}).update(
        {f"{variant}/Hat": hat_history, f"{variant}/Coat": hat_history}
    )
    versions_path.parent.mkdir(parents=True, exist_ok=True)
    versions_path.write_text(json.dumps(versions, ensure_ascii=False), encoding="utf-8")
    refer_to_asset_in_episode(project_dir, 1, "characters_in_segment", f"{variant}/Coat")
    refer_to_asset_in_episode(project_dir, 1, "characters_in_segment", f"{variant}/Hat")

    _migrate(project_dir)

    # 迁走的衍生图搬到保留名下，之后改名衍生或本体时按规范路径搬图，条目里的路径对得上。
    kept_hat_sheet = "characters/derivatives/Alice/Hat.png"
    kept = _read_json(project_dir / "project.json")["characters"]["Alice"]
    assert kept["derivatives"] == {
        "coat": {"description": "保留方的外套", "character_sheet": ""},
        "Hat": {"description": "帽子", "character_sheet": kept_hat_sheet},
    }
    assert (project_dir / kept_hat_sheet).read_bytes() == b"hat"
    [segment] = _read_json(project_dir / "scripts" / "episode_1.json")["segments"]
    assert segment["characters_in_segment"] == ["Alice/coat", "Alice/Hat"]
    assert segment["image_prompt"].startswith("@[Alice/Hat]@[Alice/coat]")
    entries = ProjectArtifactManifestAdapter(project_dir).snapshot_entries()
    assert hat_key not in entries
    assert hat_claim is not None
    assert entries[derivative_artifact_key("Alice", "Hat")] == replace(hat_claim, artifact_path=kept_hat_sheet)
    # 并入已有衍生的那条撤掉登记与历史：留着会按不区分大小写的路径占住保留方衍生的登记位。
    assert coat_key not in entries
    derivative_history = _read_json(versions_path)[CHARACTER_DERIVATIVE_RESOURCE_TYPE]
    assert f"{variant}/Hat" not in derivative_history
    assert f"{variant}/Coat" not in derivative_history
    assert derivative_history["Alice/Hat"] == hat_history
    merged = [
        params for code, _episode, params in _adjusted(project_dir) if code == "duplicate_asset_derivative_merged"
    ]
    assert merged == [
        {"name": variant, "kept": "Alice", "derivative": "Coat", "into": "coat", "folded": "true"},
        {"name": variant, "kept": "Alice", "derivative": "Hat", "into": "Hat"},
    ]
    assert "invalid_script_structure" not in _issue_codes(tmp_path)


def test_a_moved_derivative_without_its_sheet_on_disk_still_points_under_the_kept_name(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    hat = {"description": "帽子", "character_sheet": "characters/derivatives/ALICE/Hat.png"}
    characters = {"Alice": {"description": "保留"}, "ALICE": {"description": "变体", "derivatives": {"Hat": hat}}}
    (project_dir / "project.json").write_text(
        json.dumps({"schema_version": SCHEMA_V19, "characters": characters, "episodes": []}),
        encoding="utf-8",
    )

    normalize_legacy_shapes(project_dir, schema_version=SCHEMA_V19, record=[])

    # 与改名衍生一致：路径跟着本体走，不看图在不在盘上。
    [kept] = _read_json(project_dir / "project.json")["characters"].values()
    assert kept["derivatives"]["Hat"]["character_sheet"] == "characters/derivatives/Alice/Hat.png"


def test_derivatives_of_several_case_variants_fold_into_each_other(tmp_path: Path) -> None:
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    characters = {
        "Alice": {"description": "保留"},
        "ALICE": {"description": "变体", "derivatives": {"Hat": {"description": "变体的帽子", "character_sheet": ""}}},
        "alice": {"description": "变体", "derivatives": {"hat": {"description": "另一顶帽子", "character_sheet": ""}}},
    }
    (project_dir / "project.json").write_text(
        json.dumps({"schema_version": SCHEMA_V19, "characters": characters, "episodes": []}),
        encoding="utf-8",
    )

    normalize_legacy_shapes(project_dir, schema_version=SCHEMA_V19, record=[])

    # 后一条变体的 hat 与前一条迁入的 Hat 只差大小写，并入它。
    assert _read_json(project_dir / "project.json")["characters"] == {
        "Alice": {"description": "保留", "derivatives": {"Hat": {"description": "变体的帽子", "character_sheet": ""}}}
    }


def _variant_project(root: Path) -> Path:
    project_dir = _project(root)
    variant = add_asset_names_differing_only_in_case(project_dir, "characters", "character_sheet", "Alice")
    refer_to_asset_in_episode(project_dir, 1, "characters_in_segment", variant)
    return project_dir


def _fail_committing_without_variant(patch: pytest.MonkeyPatch) -> None:
    """让去掉变体 ``ALICE`` 的那次 ``project.json`` 写盘失败：引用已改写落盘，资产表还没提交。"""

    write = legacy_shapes.atomic_write_json

    def fail_without_variant(path: Path, payload: Any) -> None:
        if path.name == "project.json" and "ALICE" not in payload.get("characters", {}):
            raise OSError("disk full")
        write(path, payload)

    patch.setattr(legacy_shapes, "atomic_write_json", fail_without_variant)


def _migrated_state(project_dir: Path) -> tuple[Any, ...]:
    report = load_migration_report(project_dir)
    assert report is not None
    return (
        {key: value for key, value in _read_json(project_dir / "project.json").items() if key != "episodes"},
        _read_json(project_dir / "scripts" / "episode_1.json"),
        _read_json(project_dir / "drafts" / "episode_1" / "script_plan_segments.json"),
        # 中途失败时先落盘的改动先记下，重跑后报告里的先后与一次跑完不同，内容一致。
        sorted((item.code, item.episode or 0, sorted(item.params.items())) for item in report.adjusted),
    )


def test_a_normalization_that_fails_after_rewriting_references_converges_on_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    once = _variant_project(tmp_path / "once")
    _migrate(once)
    retried = _variant_project(tmp_path / "retried")

    # 引用已改写落盘、资产表还没提交时失败：重跑仍能发现变体，结果与一次跑完一致。
    with monkeypatch.context() as patch:
        _fail_committing_without_variant(patch)
        assert migrate_project_with_verdict(retried) is not None
    assert "ALICE" in _read_json(retried / "project.json")["characters"]
    _migrate(retried)

    assert _migrated_state(retried) == _migrated_state(once)


@pytest.mark.parametrize("fails_once", [False, True], ids=["one-pass", "retried"])
def test_a_confirmed_script_plan_stays_confirmed_after_its_references_are_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fails_once: bool
) -> None:
    project_dir = _project(tmp_path)
    variant = add_asset_names_differing_only_in_case(project_dir, "characters", "character_sheet", "Alice")
    refer_to_asset_in_episode(project_dir, 1, "characters_in_segment", variant)
    plan_path = project_dir / "drafts" / "episode_1" / "script_plan_segments.json"
    project = _read_json(project_dir / "project.json")
    project["episodes"][0]["script_plan_review"] = {
        "fingerprint": content_fingerprint(plan_path),
        "confirmed_at": "2026-03-02T14:56:52Z",
    }
    (project_dir / "project.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")

    if fails_once:
        with monkeypatch.context() as patch:
            _fail_committing_without_variant(patch)
            assert migrate_project_with_verdict(project_dir) is not None
    _migrate(project_dir)

    assert _read_json(plan_path)["segments"][0]["characters_in_segment"] == ["Alice"]
    [entry] = _read_json(project_dir / "project.json")["episodes"]
    assert entry["script_plan_review"] == {
        "fingerprint": content_fingerprint(plan_path),
        "confirmed_at": "2026-03-02T14:56:52Z",
    }


def test_missing_and_duplicate_item_ids_are_reassigned_and_the_original_media_stays_with_the_first(
    tmp_path: Path,
) -> None:
    project_dir = _project(tmp_path)
    break_script_item_ids(project_dir, 1)

    _migrate(project_dir)

    segments = _read_json(project_dir / "scripts" / "episode_1.json")["segments"]
    assert [segment["segment_id"] for segment in segments] == ["E1S01", "E1S02", "E1S03"]
    assert segments[0]["generated_assets"]["storyboard_image"] == "storyboards/scene_E1S01.png"
    assert segments[1]["generated_assets"]["storyboard_image"] is None
    assert segments[1]["image_prompt"] == "另一镜"
    assert _adjusted(project_dir) == [
        ("item_id_reassigned", 1, {"from": "E1S01", "to": "E1S02"}),
        ("item_id_reassigned", 1, {"from": "", "to": "E1S03"}),
    ]
    assert (project_dir / "storyboards" / "scene_E1S01.png").is_file()


def test_a_renumbered_item_lets_go_of_the_end_frame_that_belongs_to_the_original_id(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    end_frame = resource_relative_path(END_FRAME_RESOURCE_TYPE, "E1S01")
    script_path = project_dir / "scripts" / "episode_1.json"
    script = _read_json(script_path)
    script["segments"][0]["end_frame_image"] = end_frame
    script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    break_script_item_ids(project_dir, 1)

    _migrate(project_dir)

    first, renumbered, _ = _read_json(script_path)["segments"]
    assert first["end_frame_image"] == end_frame
    assert renumbered["segment_id"] == "E1S02"
    assert "end_frame_image" not in renumbered


def test_a_renumbered_item_reads_as_not_yet_generated(tmp_path: Path) -> None:
    """换号条目不带走原 id 那一条的缩略图、视频 URI、宫格归属与生成时刻，落盘的状态也复位。"""
    project_dir = _project(tmp_path)
    script_path = project_dir / "scripts" / "episode_1.json"
    script = _read_json(script_path)
    generated = {
        "storyboard_image": "storyboards/scene_E1S01.png",
        "storyboard_last_image": "storyboards/scene_E1S01_last.png",
        "grid_id": "grid_123456789abc",
        "grid_cell_index": 0,
        "video_clip": "videos/scene_E1S01.mp4",
        "video_thumbnail": "thumbnails/scene_E1S01.jpg",
        "video_uri": "https://example.com/E1S01.mp4",
        "video_generated_at": "2026-01-01T00:00:00Z",
        "status": "completed",
    }
    script["segments"][0]["generated_assets"] = dict(generated)
    script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    (project_dir / "videos").mkdir(exist_ok=True)
    (project_dir / "videos" / "scene_E1S01.mp4").write_bytes(b"video")
    break_script_item_ids(project_dir, 1)

    _migrate(project_dir)

    first, renumbered, _ = _read_json(script_path)["segments"]
    assert first["generated_assets"] == generated
    assert renumbered["segment_id"] == "E1S02"
    assert {key: value for key, value in renumbered["generated_assets"].items() if value is not None} == {
        "status": "pending"
    }


@pytest.mark.parametrize(
    ("item_id", "owner", "renumbered_to"),
    [
        pytest.param("E2S01", 2, ("E1S01", 1), id="the-episode-the-id-prefix-names"),
        pytest.param("S01", 1, ("E2S01", 2), id="the-first-episode-in-the-ledger"),
    ],
)
def test_an_item_id_two_episodes_share_stays_with_one_and_is_renumbered_in_the_other(
    tmp_path: Path, item_id: str, owner: int, renumbered_to: tuple[str, int]
) -> None:
    project_dir = _project(tmp_path)
    reuse_item_id_across_episodes(project_dir, item_id)
    # 两集认领同一个文件时清单只容得下一条登记：生成它的是 id 前缀所指的那一集。
    _register_test_claim(
        project_dir, ArtifactKey.episode_storyboard(owner, item_id), f"storyboards/scene_{item_id}.png"
    )

    _migrate(project_dir)

    new_id, other = renumbered_to
    owned = _read_json(project_dir / "scripts" / f"episode_{owner}.json")["segments"][0]
    moved = _read_json(project_dir / "scripts" / f"episode_{other}.json")["segments"][0]
    assert (owned["segment_id"], owned["generated_assets"]["storyboard_image"]) == (
        item_id,
        f"storyboards/scene_{item_id}.png",
    )
    assert (moved["segment_id"], moved["generated_assets"]["storyboard_image"]) == (new_id, None)
    assert (project_dir / "storyboards" / f"scene_{item_id}.png").read_bytes() == b"shared storyboard"
    assert ("item_id_reassigned", other, {"from": item_id, "to": new_id}) in _adjusted(project_dir)
    entries = ProjectArtifactManifestAdapter(project_dir).snapshot_entries()
    assert ArtifactKey.episode_storyboard(owner, item_id) in entries
    assert ArtifactKey.episode_storyboard(other, item_id) not in entries


def _manual_archive(project_dir: Path, archive_path: Path) -> Path:
    """手工打包的归档：项目目录下的可见文件原样入包，不带信封与隐藏的产物清单。"""
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(project_dir.rglob("*")):
            relative = item.relative_to(project_dir)
            if item.is_file() and not any(part.startswith(".") for part in relative.parts):
                archive.write(item, arcname=relative.as_posix())
    return archive_path


def _import_report(tmp_path: Path, project_dir: Path) -> tuple[ProjectManager, Path, MigrationReport]:
    """导入 ``project_dir`` 的手工归档：先拿到要求确认的报告（不留项目），再确认导入，返回装好的项目目录。"""
    archive = _manual_archive(project_dir, tmp_path / "v19.zip")
    target = ProjectManager(tmp_path / "target")
    with pytest.raises(ProjectArchiveValidationError) as exc_info:
        ProjectArchiveService(target).import_project_archive(archive, uploaded_filename="v19.zip")
    assert exc_info.value.status_code == 409
    assert target.list_projects() == []
    report = MigrationReport.model_validate(exc_info.value.extra["migration_report"])
    result = ProjectArchiveService(target).import_project_archive(
        archive, uploaded_filename="v19.zip", confirm_report=True
    )
    return target, target.get_project_path(result.project_name), report


def test_a_corrupt_grid_record_in_an_imported_v19_project_is_kept_as_is_and_reported(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    write_unreadable_grid_record(project_dir)

    _, imported, report = _import_report(tmp_path, project_dir)

    assert (imported / "grids" / "grid_0123456789ab.json").read_bytes() == b"{not json"
    assert ("episode-grid", "grids/grid_0123456789ab.json") in [
        (item.kind, item.artifact_path) for item in report.skipped
    ]


def test_a_corrupt_script_plan_draft_in_an_imported_v19_project_is_kept_as_is_and_reported(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    write_unreadable_script_plan_draft(project_dir, 1, "script_plan_segments.json")

    _, imported, report = _import_report(tmp_path, project_dir)

    assert (imported / "drafts" / "episode_1" / "script_plan_segments.json").read_bytes() == b"{not json"
    assert ("episode-script-plan", "drafts/episode_1/script_plan_segments.json") in [
        (item.kind, item.artifact_path) for item in report.skipped
    ]
    assert ArtifactKey.episode_script(1) in ProjectArtifactManifestAdapter(imported).snapshot_entries()


def test_narration_audio_without_tts_settings_in_an_imported_v19_project_is_reported_as_legacy(
    tmp_path: Path,
) -> None:
    """v19 仍带着没有 TTS 设置的旧旁白记录：导入激活不登记它们，报告「未能带入」并归为旧版配音。"""
    project_dir = write_legacy_tts_narration_project(tmp_path / "projects", with_tts_settings=False)

    _, imported, report = _import_report(tmp_path, project_dir)

    legacy = {item.resource_id for item in report.skipped if item.category == "legacy_audio_basis"}
    assert legacy == {"E1S1", "E1S2"}
    entries = ProjectArtifactManifestAdapter(imported).snapshot_entries()
    assert ArtifactKey.episode_audio(1, "E1S1") not in entries
    assert (imported / "audio" / "segment_E1S1.wav").read_bytes() == b"tts-E1S1"


def test_adjustments_survive_a_chain_that_fails_and_is_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir = _project(tmp_path)
    add_colliding_asset_name(project_dir, "characters", "阿离")

    def fail(_step: Any, _project_dir: Path, **_kwargs: Any) -> object:
        raise ProjectMigrationError("the step after the normalization failed", file="project.json")

    # 规整之后那一步失败：链停在半路，已做的规整写进未完成的报告。
    with monkeypatch.context() as patch:
        wrap_the_last_migration_step(patch, fail)
        assert migrate_project_with_verdict(project_dir) is not None
    unfinished = load_migration_report(project_dir)
    assert unfinished is not None
    assert not unfinished.complete
    assert [item.code for item in unfinished.adjusted] == ["duplicate_asset_removed"]

    _migrate(project_dir)

    assert [code for code, *_ in _adjusted(project_dir)] == ["duplicate_asset_removed"]


def test_adjustments_already_on_disk_survive_a_normalization_that_fails_halfway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = _project(tmp_path)
    set_script_episode(project_dir, 1, None)
    break_script_item_ids(project_dir, 1)
    write = legacy_shapes.atomic_write_json
    script_writes = 0

    def fail_on_second_script_write(path: Path, payload: Any) -> None:
        nonlocal script_writes
        if path.name == "episode_1.json":
            script_writes += 1
            if script_writes == 2:
                raise OSError("disk full")
        write(path, payload)

    # 剧本集号已写回盘上，之后换条目 id 时写盘失败：重跑时规整发现不了集号的改动，只能靠未完成的报告带过去。
    with monkeypatch.context() as patch:
        patch.setattr(legacy_shapes, "atomic_write_json", fail_on_second_script_write)
        assert migrate_project_with_verdict(project_dir) is not None
    unfinished = load_migration_report(project_dir)
    assert unfinished is not None
    assert not unfinished.complete
    assert [item.code for item in unfinished.adjusted] == ["script_episode_corrected"]

    _migrate(project_dir)

    assert _adjusted(project_dir) == [
        ("script_episode_corrected", 1, {"from": "", "to": "1"}),
        ("item_id_reassigned", 1, {"from": "E1S01", "to": "E1S02"}),
        ("item_id_reassigned", 1, {"from": "", "to": "E1S03"}),
    ]


def test_adjustments_survive_a_last_step_that_fails_after_committing_the_current_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """最后一步写下当前版本后才失败：重跑不再进链，未完成的报告补写成完成的报告，照常显示。"""
    project_dir = _project(tmp_path)
    add_colliding_asset_name(project_dir, "characters", "阿离")

    def commit_then_fail(step: Any, path: Path, **kwargs: Any) -> object:
        step(path, **kwargs)
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        wrap_the_last_migration_step(patch, commit_then_fail)
        assert migrate_project_with_verdict(project_dir) is not None
    assert _read_json(project_dir / "project.json")["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION
    assert visible_migration_report(project_dir) is None

    _migrate(project_dir)

    report = visible_migration_report(project_dir)
    assert report is not None
    assert report.to_schema_version == CURRENT_PROJECT_SCHEMA_VERSION
    assert [code for code, *_ in _adjusted(project_dir)] == ["duplicate_asset_removed"]


def test_adjustments_survive_a_failed_final_report_write_and_show_after_the_next_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """链走完、收尾那次写报告失败：调整留在未完成的报告里，下次启动扫描时补写成完成的报告。"""
    project_dir = _project(tmp_path)
    add_colliding_asset_name(project_dir, "characters", "阿离")
    write = runner.write_migration_report

    def fail_complete_report(path: Path, report: MigrationReport) -> None:
        if report.complete:
            raise OSError("disk full")
        write(path, report)

    with monkeypatch.context() as patch:
        patch.setattr(runner, "write_migration_report", fail_complete_report)
        assert migrate_project_with_verdict(project_dir) is not None
    unfinished = load_migration_report(project_dir)
    assert unfinished is not None
    assert not unfinished.complete

    summary = runner.run_project_migrations(project_dir.parent)

    assert summary.skipped == [project_dir.name]
    assert visible_migration_report(project_dir) is not None
    assert [code for code, *_ in _adjusted(project_dir)] == ["duplicate_asset_removed"]


def test_the_status_shows_the_report_until_it_is_acknowledged(tmp_path: Path) -> None:
    project_dir = _project(tmp_path)
    add_colliding_asset_name(project_dir, "characters", "阿离")
    _migrate(project_dir)
    service = WorkflowStateService(ProjectManager(str(tmp_path)))

    shown = service.get_status("demo").migration_report
    assert shown is not None
    assert [item.code for item in shown.adjusted] == ["duplicate_asset_removed"]

    assert acknowledge_migration_report(project_dir) is True
    assert service.get_status("demo").migration_report is None
