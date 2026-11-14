"""校验器报出缺失引用时一并交出它们，供归档导出清掉悬空引用；不带收集器时什么都不记。"""

from __future__ import annotations

import json
from pathlib import Path

from lib.project.data_validator import DataValidator, MissingReference
from lib.project.project_migrations.runner import migrate_project_with_verdict
from tests.legacy_project_shapes import write_legacy_storyboard_project


def _project_missing_a_storyboard(root: Path) -> Path:
    project_dir = write_legacy_storyboard_project(root / "projects", name="demo")
    assert migrate_project_with_verdict(project_dir) is None
    (project_dir / "storyboards" / "scene_E1S1.png").unlink()
    return project_dir


def test_missing_references_are_collected_with_their_document_and_field(tmp_path: Path) -> None:
    project_dir = _project_missing_a_storyboard(tmp_path)
    found: list[MissingReference] = []

    DataValidator().validate_project_tree(project_dir, missing_references=found)

    assert [(item.document, item.field, item.path) for item in found] == [
        ("scripts/episode_1.json", "segments[0].generated_assets.storyboard_image", "storyboards/scene_E1S1.png")
    ]
    document = found[0].clear()
    assert document["segments"][0]["generated_assets"]["storyboard_image"] is None


def test_a_later_validation_without_a_collector_records_nothing(tmp_path: Path) -> None:
    project_dir = _project_missing_a_storyboard(tmp_path)
    found: list[MissingReference] = []
    validator = DataValidator()

    validator.validate_project_tree(project_dir, missing_references=found)
    # 只校验单个剧本的入口不经过 validate_project_tree：收集器若没在上一次结束时撤下，这里会往旧清单里记
    validator.validate_episode_file(project_dir, "scripts/episode_1.json")
    validator.validate_project_tree(project_dir)

    assert len(found) == 1


def test_other_reference_errors_are_not_collected(tmp_path: Path) -> None:
    project_dir = write_legacy_storyboard_project(tmp_path / "projects", name="demo")
    assert migrate_project_with_verdict(project_dir) is None
    script_path = project_dir / "scripts" / "episode_1.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    script["segments"][0]["end_frame_image"] = "storyboards/scene_E1S1.png"
    script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    found: list[MissingReference] = []

    result = DataValidator().validate_project_tree(project_dir, missing_references=found)

    assert not result.valid
    assert found == []
