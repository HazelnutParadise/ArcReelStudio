"""可以协作的编辑单元：各自从项目文件读出的内容，以及写回走与 REST 同一套修改逻辑。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from lib.project.project_manager import ProjectManager
from server.services.collab.units import PROJECT_UNIT_SPECS, UnitNotFoundError, UnitWriteError

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
def unit_project_files(tmp_path: Path) -> ProjectManager:
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


def test_overview_reads_every_field_and_writes_trimmed_text(unit_project_files) -> None:
    unit = PROJECT_UNIT_SPECS["overview"]

    unit.write(unit_project_files, PROJECT, "", {"synopsis": "  雨夜的故事  "})

    assert unit.read(unit_project_files, PROJECT, "") == {
        "synopsis": "雨夜的故事",
        "genre": "",
        "theme": "",
        "world_setting": "",
    }


def test_brief_rejects_an_invalid_target_duration(unit_project_files) -> None:
    unit = PROJECT_UNIT_SPECS["brief"]

    unit.write(unit_project_files, PROJECT, "", {"brief": "清爽一夏", "target_duration": 30})
    assert unit.read(unit_project_files, PROJECT, "") == {"brief": "清爽一夏", "target_duration": 30}

    with pytest.raises(UnitWriteError) as exc:
        unit.write(unit_project_files, PROJECT, "", {"target_duration": 0})
    assert exc.value.code == "target_duration_invalid"


def test_character_fields_round_trip(unit_project_files) -> None:
    unit = PROJECT_UNIT_SPECS["asset"]

    assert unit.read(unit_project_files, PROJECT, "character:Alice") == {"description": "高个子", "voice_style": "低沉"}
    unit.write(unit_project_files, PROJECT, "character:Alice", {"description": "矮个子"})

    assert unit.read(unit_project_files, PROJECT, "character:Alice")["description"] == "矮个子"


def test_product_selling_points_are_one_per_line(unit_project_files) -> None:
    unit = PROJECT_UNIT_SPECS["asset"]

    unit.write(unit_project_files, PROJECT, "product:Tea", {"selling_points": "回甘\n\n  无糖  \n"})

    assert unit_project_files.load_project(PROJECT)["products"]["Tea"]["selling_points"] == ["回甘", "无糖"]
    assert unit.read(unit_project_files, PROJECT, "product:Tea")["selling_points"] == "回甘\n无糖"


@pytest.mark.parametrize("key", ["character:Nobody", "nonsense", "dragon:Alice"])
def test_missing_assets_are_reported_as_not_found(unit_project_files, key) -> None:
    with pytest.raises(UnitNotFoundError):
        PROJECT_UNIT_SPECS["asset"].read(unit_project_files, PROJECT, key)


def test_derivative_description_round_trips(unit_project_files) -> None:
    unit_project_files.update_asset_entry(
        "character", PROJECT, "Alice", lambda entry: entry.update({"derivatives": {"少年": {"description": "十岁"}}})
    )
    unit = PROJECT_UNIT_SPECS["derivative"]

    unit.write(unit_project_files, PROJECT, "Alice/少年", {"description": "十二岁"})

    assert unit.read(unit_project_files, PROJECT, "Alice/少年") == {"description": "十二岁"}
    with pytest.raises(UnitNotFoundError):
        unit.read(unit_project_files, PROJECT, "Alice/老年")


def test_script_item_reads_its_whitelisted_fields_and_writes_through_the_batch_editor(unit_project_files) -> None:
    unit = PROJECT_UNIT_SPECS["script_item"]
    content = unit.read(unit_project_files, PROJECT, "episode_1.json#E1S01")

    assert "generated_assets" not in content
    assert content["novel_text"] == "风吹过旷野。"

    unit.write(unit_project_files, PROJECT, "episode_1.json#E1S01", {"novel_text": "雨落在旷野上。", "note": "放慢"})

    saved = unit_project_files.load_script(PROJECT, "episode_1.json")["segments"][0]
    assert saved["novel_text"] == "雨落在旷野上。"
    assert saved["note"] == "放慢"
    # 没提交的字段原样保留
    assert saved["image_prompt"]["scene"] == "荒野"


def test_script_item_ignores_fields_outside_the_whitelist(unit_project_files) -> None:
    unit = PROJECT_UNIT_SPECS["script_item"]

    unit.write(unit_project_files, PROJECT, "episode_1.json#E1S01", {"generated_assets": {"status": "done"}})

    assert unit_project_files.load_script(PROJECT, "episode_1.json")["segments"][0]["generated_assets"] == {}


def test_a_missing_script_item_is_reported_as_not_found(unit_project_files) -> None:
    with pytest.raises(UnitNotFoundError):
        PROJECT_UNIT_SPECS["script_item"].read(unit_project_files, PROJECT, "episode_1.json#E1S99")


def test_own_episode_source_round_trips(unit_project_files) -> None:
    unit_project_files.update_project(PROJECT, lambda data: data.update({"episodes": [{"episode": 2, "title": "二"}]}))
    unit = PROJECT_UNIT_SPECS["episode_source"]

    assert unit.read(unit_project_files, PROJECT, "2") == {"text": ""}
    unit.write(unit_project_files, PROJECT, "2", {"text": "第二集原文"})

    assert unit.read(unit_project_files, PROJECT, "2")["text"].strip() == "第二集原文"
    stored = json.loads((unit_project_files.get_project_path(PROJECT) / "project.json").read_text(encoding="utf-8"))
    assert stored["episodes"][0]["source_origin"] == "own"


def test_a_derived_episode_source_cannot_be_written(unit_project_files) -> None:
    unit_project_files.update_project(
        PROJECT,
        lambda data: data.update({"episodes": [{"episode": 3, "title": "三", "source_origin": "whole_source"}]}),
    )

    with pytest.raises(UnitWriteError) as exc:
        PROJECT_UNIT_SPECS["episode_source"].write(unit_project_files, PROJECT, "3", {"text": "改不了"})
    assert exc.value.code == "episode_source_derived"


def test_page_rooms_carry_no_content_and_need_an_existing_project(unit_project_files) -> None:
    unit = PROJECT_UNIT_SPECS["page"]

    assert unit.read(unit_project_files, PROJECT, "/app/projects/demo") == {}
    unit.write(unit_project_files, PROJECT, "/app/projects/demo", {"anything": "x"})
    with pytest.raises(UnitNotFoundError):
        unit.read(unit_project_files, "missing", "/app/projects/missing")
    with pytest.raises(UnitNotFoundError):
        unit.read(unit_project_files, PROJECT, "not-a-path")


# ── 项目设置 ──────────────────────────────────────────────────────


def test_project_settings_reads_the_settable_fields_under_their_stored_names(unit_project_files) -> None:
    unit_project_files.update_project(
        PROJECT, lambda data: data.update({"aspect_ratio": "16:9", "style_image": "style_reference.png"})
    )

    settings = PROJECT_UNIT_SPECS["project_settings"].read(unit_project_files, PROJECT, "")

    assert settings["aspect_ratio"] == "16:9"
    assert settings["style_image"] == "style_reference.png"
    assert settings["video_backend"] is None
    assert "clear_style_image" not in settings
    assert "title" not in settings


def test_project_settings_writes_through_the_same_rules_as_the_project_patch(unit_project_files) -> None:
    unit = PROJECT_UNIT_SPECS["project_settings"]

    unit.write(unit_project_files, PROJECT, "", {"aspect_ratio": "16:9", "speech_rate_units_per_second": 4.5})

    project = unit_project_files.load_project(PROJECT)
    assert project["aspect_ratio"] == "16:9"
    assert project["speech_rate_units_per_second"] == 4.5


def test_project_settings_clearing_the_style_image_removes_it_with_its_description(unit_project_files) -> None:
    unit_project_files.update_project(
        PROJECT, lambda data: data.update({"style_image": "style_reference.png", "style_description": "水彩"})
    )

    PROJECT_UNIT_SPECS["project_settings"].write(unit_project_files, PROJECT, "", {"style_image": ""})

    project = unit_project_files.load_project(PROJECT)
    assert "style_image" not in project
    assert "style_description" not in project


def test_project_settings_rejects_what_the_patch_rejects_with_its_message_key(unit_project_files) -> None:
    with pytest.raises(UnitWriteError) as exc:
        PROJECT_UNIT_SPECS["project_settings"].write(
            unit_project_files, PROJECT, "", {"speech_rate_units_per_second": 999.0}
        )

    assert exc.value.code == "speech_rate_out_of_range"
    assert set(exc.value.params) == {"min", "max"}
    assert "speech_rate_units_per_second" not in unit_project_files.load_project(PROJECT)


@pytest.mark.parametrize("field", ["video_backend", "image_provider_t2i", "default_text_backend", "audio_backend"])
def test_project_settings_rejects_a_provider_without_a_model(unit_project_files, field) -> None:
    """协作写回与项目 PATCH 同一套校验：模型字段只写了内置供应商被拒，不落盘（docs/adr/0130）。"""
    with pytest.raises(UnitWriteError) as exc:
        PROJECT_UNIT_SPECS["project_settings"].write(unit_project_files, PROJECT, "", {field: "gemini-aistudio"})

    assert exc.value.code == "invalid_backend_format"
    assert field not in unit_project_files.load_project(PROJECT)


def test_project_settings_ignores_derived_fields_written_by_the_browser(unit_project_files) -> None:
    PROJECT_UNIT_SPECS["project_settings"].write(
        unit_project_files, PROJECT, "", {"style_image": "elsewhere.png", "style_description": "改不到"}
    )

    project = unit_project_files.load_project(PROJECT)
    assert "style_image" not in project
    assert "style_description" not in project
