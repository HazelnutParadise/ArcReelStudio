"""可以协作的编辑单元：各自从项目文件读出的内容，以及写回走与 REST 同一套修改逻辑。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lib.project.project_manager import ProjectManager
from server.services.collab.units import UNIT_SPECS, UnitNotFoundError, UnitWriteError

PROJECT = "demo"


def _segment(segment_id: str) -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "duration_seconds": 4,
        "novel_text": "风吹过旷野。",
        "characters_in_segment": [],
        "image_prompt": {
            "scene": "荒野",
            "composition": {"shot_type": "Medium Shot", "lighting": "暖光", "ambiance": "薄雾"},
        },
        "video_prompt": {"action": "转身", "camera_motion": "Static", "ambiance_audio": "风声"},
        "generated_assets": {},
    }


@pytest.fixture
def project_files(tmp_path: Path) -> ProjectManager:
    pm = ProjectManager(str(tmp_path))
    pm.create_project(PROJECT, content_mode="narration")
    pm.create_project_metadata(PROJECT, "Demo", "Anime", "narration")
    pm.save_script(
        PROJECT,
        {
            "episode": 1,
            "title": "第一集",
            "content_mode": "narration",
            "summary": "摘要",
            "novel": {"title": "小说", "chapter": "第一章"},
            "segments": [_segment("E1S01"), _segment("E1S02")],
        },
        "episode_1.json",
    )
    pm.add_character(PROJECT, "Alice", "高个子", "低沉")
    pm.add_product(PROJECT, "Tea", "绿茶", "山野")
    return pm


def test_overview_reads_every_field_and_writes_trimmed_text(project_files) -> None:
    unit = UNIT_SPECS["overview"]

    unit.write(project_files, PROJECT, "", {"synopsis": "  雨夜的故事  "})

    assert unit.read(project_files, PROJECT, "") == {
        "synopsis": "雨夜的故事",
        "genre": "",
        "theme": "",
        "world_setting": "",
    }


def test_brief_rejects_an_invalid_target_duration(project_files) -> None:
    unit = UNIT_SPECS["brief"]

    unit.write(project_files, PROJECT, "", {"brief": "清爽一夏", "target_duration": 30})
    assert unit.read(project_files, PROJECT, "") == {"brief": "清爽一夏", "target_duration": 30}

    with pytest.raises(UnitWriteError) as exc:
        unit.write(project_files, PROJECT, "", {"target_duration": 0})
    assert exc.value.code == "target_duration_invalid"


def test_character_fields_round_trip(project_files) -> None:
    unit = UNIT_SPECS["asset"]

    assert unit.read(project_files, PROJECT, "character:Alice") == {"description": "高个子", "voice_style": "低沉"}
    unit.write(project_files, PROJECT, "character:Alice", {"description": "矮个子"})

    assert unit.read(project_files, PROJECT, "character:Alice")["description"] == "矮个子"


def test_product_selling_points_are_one_per_line(project_files) -> None:
    unit = UNIT_SPECS["asset"]

    unit.write(project_files, PROJECT, "product:Tea", {"selling_points": "回甘\n\n  无糖  \n"})

    assert project_files.load_project(PROJECT)["products"]["Tea"]["selling_points"] == ["回甘", "无糖"]
    assert unit.read(project_files, PROJECT, "product:Tea")["selling_points"] == "回甘\n无糖"


@pytest.mark.parametrize("key", ["character:Nobody", "nonsense", "dragon:Alice"])
def test_missing_assets_are_reported_as_not_found(project_files, key) -> None:
    with pytest.raises(UnitNotFoundError):
        UNIT_SPECS["asset"].read(project_files, PROJECT, key)


def test_derivative_description_round_trips(project_files) -> None:
    project_files.update_asset_entry(
        "character", PROJECT, "Alice", lambda entry: entry.update({"derivatives": {"少年": {"description": "十岁"}}})
    )
    unit = UNIT_SPECS["derivative"]

    unit.write(project_files, PROJECT, "Alice/少年", {"description": "十二岁"})

    assert unit.read(project_files, PROJECT, "Alice/少年") == {"description": "十二岁"}
    with pytest.raises(UnitNotFoundError):
        unit.read(project_files, PROJECT, "Alice/老年")


def test_script_item_reads_its_whitelisted_fields_and_writes_through_the_batch_editor(project_files) -> None:
    unit = UNIT_SPECS["script_item"]
    content = unit.read(project_files, PROJECT, "episode_1.json#E1S01")

    assert "generated_assets" not in content
    assert content["novel_text"] == "风吹过旷野。"

    unit.write(project_files, PROJECT, "episode_1.json#E1S01", {"novel_text": "雨落在旷野上。", "note": "放慢"})

    saved = project_files.load_script(PROJECT, "episode_1.json")["segments"][0]
    assert saved["novel_text"] == "雨落在旷野上。"
    assert saved["note"] == "放慢"
    # 没提交的字段原样保留
    assert saved["image_prompt"]["scene"] == "荒野"


def test_script_item_ignores_fields_outside_the_whitelist(project_files) -> None:
    unit = UNIT_SPECS["script_item"]

    unit.write(project_files, PROJECT, "episode_1.json#E1S01", {"generated_assets": {"status": "done"}})

    assert project_files.load_script(PROJECT, "episode_1.json")["segments"][0]["generated_assets"] == {}


def test_a_missing_script_item_is_reported_as_not_found(project_files) -> None:
    with pytest.raises(UnitNotFoundError):
        UNIT_SPECS["script_item"].read(project_files, PROJECT, "episode_1.json#E1S99")


def test_own_episode_source_round_trips(project_files) -> None:
    project_files.update_project(PROJECT, lambda data: data.update({"episodes": [{"episode": 2, "title": "二"}]}))
    unit = UNIT_SPECS["episode_source"]

    assert unit.read(project_files, PROJECT, "2") == {"text": ""}
    unit.write(project_files, PROJECT, "2", {"text": "第二集原文"})

    assert unit.read(project_files, PROJECT, "2")["text"].strip() == "第二集原文"
    stored = json.loads((project_files.get_project_path(PROJECT) / "project.json").read_text(encoding="utf-8"))
    assert stored["episodes"][0]["source_origin"] == "own"


def test_a_derived_episode_source_cannot_be_written(project_files) -> None:
    project_files.update_project(
        PROJECT,
        lambda data: data.update({"episodes": [{"episode": 3, "title": "三", "source_origin": "whole_source"}]}),
    )

    with pytest.raises(UnitWriteError) as exc:
        UNIT_SPECS["episode_source"].write(project_files, PROJECT, "3", {"text": "改不了"})
    assert exc.value.code == "episode_source_derived"


def test_page_rooms_carry_no_content_and_need_an_existing_project(project_files) -> None:
    unit = UNIT_SPECS["page"]

    assert unit.read(project_files, PROJECT, "/app/projects/demo") == {}
    unit.write(project_files, PROJECT, "/app/projects/demo", {"anything": "x"})
    with pytest.raises(UnitNotFoundError):
        unit.read(project_files, "missing", "/app/projects/missing")
    with pytest.raises(UnitNotFoundError):
        unit.read(project_files, PROJECT, "not-a-path")
