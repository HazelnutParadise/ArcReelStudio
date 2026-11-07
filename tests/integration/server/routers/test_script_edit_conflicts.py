"""分镜详情的保存带上编辑起点（``base``）：起点之后被其他成员改过的字段拒绝写入，不覆盖对方。

只核对这次要写的字段；起点里其余字段即使已经过时也不影响保存。不带 ``base`` 的旧请求照旧直接写入。
"""

from __future__ import annotations

import unicodedata
from copy import deepcopy

import pytest

from tests.integration.server.routers.projects_router_support import _FakePM, build_projects_client

_NARRATION = {
    "content_mode": "narration",
    "segments": [
        {
            "segment_id": "E1S01",
            "duration_seconds": 4,
            "image_prompt": "原来的画面",
            "video_prompt": "原来的运镜",
            "characters_in_segment": ["Alice"],
        }
    ],
}
_DRAMA = {
    "content_mode": "drama",
    "scenes": [{"scene_id": "001", "duration_seconds": 8, "image_prompt": "原来的画面", "video_prompt": {}}],
}
_AD = {
    "content_mode": "ad",
    "shots": [{"shot_id": "S1", "section": "hook", "voiceover_text": "原来的口播", "duration_seconds": 3}],
}


@pytest.fixture
def scripts(tmp_path, monkeypatch):
    fake_pm = _FakePM(tmp_path)
    fake_pm.scripts[("ready", "narration.json")] = deepcopy(_NARRATION)
    fake_pm.scripts[("ready", "drama.json")] = deepcopy(_DRAMA)
    fake_pm.scripts[("ready", "ad.json")] = deepcopy(_AD)
    with build_projects_client(monkeypatch, fake_pm) as client:
        yield client, fake_pm.scripts


def _segment(scripts) -> dict:
    return scripts[("ready", "narration.json")]["segments"][0]


def test_a_save_based_on_the_current_value_is_written(scripts):
    client, stored = scripts

    response = client.patch(
        "/api/v1/projects/ready/segments/E1S01",
        json={"script_file": "narration.json", "image_prompt": "新的画面", "base": {"image_prompt": "原来的画面"}},
    )

    assert response.status_code == 200
    assert _segment(stored)["image_prompt"] == "新的画面"


def test_a_field_changed_by_someone_else_since_the_edit_began_is_not_overwritten(scripts):
    client, stored = scripts
    _segment(stored)["image_prompt"] = "别人刚改的画面"

    response = client.patch(
        "/api/v1/projects/ready/segments/E1S01",
        json={"script_file": "narration.json", "image_prompt": "我的画面", "base": {"image_prompt": "原来的画面"}},
    )

    assert response.status_code == 409
    assert response.json()["diagnostic"] == {"code": "edit_conflict", "fields": ["image_prompt"]}
    assert _segment(stored)["image_prompt"] == "别人刚改的画面"


def test_only_the_fields_being_saved_are_checked(scripts):
    client, stored = scripts
    _segment(stored)["video_prompt"] = "别人刚改的运镜"

    response = client.patch(
        "/api/v1/projects/ready/segments/E1S01",
        json={
            "script_file": "narration.json",
            "image_prompt": "我的画面",
            "base": {"image_prompt": "原来的画面", "video_prompt": "原来的运镜"},
        },
    )

    assert response.status_code == 200
    assert _segment(stored)["image_prompt"] == "我的画面"
    assert _segment(stored)["video_prompt"] == "别人刚改的运镜"


def test_reference_lists_compare_by_asset_name_key(scripts):
    """同一个资产名的不同 Unicode 写法（NFC 与 NFD）视为同一个值，不算被别人改过。"""
    client, stored = scripts
    _segment(stored)["characters_in_segment"] = [unicodedata.normalize("NFC", "Café")]

    response = client.patch(
        "/api/v1/projects/ready/segments/E1S01",
        json={
            "script_file": "narration.json",
            "characters_in_segment": ["Café", "Bob"],
            "base": {"characters_in_segment": [unicodedata.normalize("NFD", "Café")]},
        },
    )

    assert response.status_code == 200


def test_saves_without_a_starting_point_keep_the_previous_behaviour(scripts):
    client, stored = scripts
    _segment(stored)["image_prompt"] = "别人刚改的画面"

    response = client.patch(
        "/api/v1/projects/ready/segments/E1S01",
        json={"script_file": "narration.json", "image_prompt": "我的画面"},
    )

    assert response.status_code == 200
    assert _segment(stored)["image_prompt"] == "我的画面"


def test_drama_scenes_reject_stale_saves(scripts):
    client, stored = scripts
    stored[("ready", "drama.json")]["scenes"][0]["duration_seconds"] = 6

    response = client.patch(
        "/api/v1/projects/ready/script-scenes/001",
        json={"script_file": "drama.json", "updates": {"duration_seconds": 10}, "base": {"duration_seconds": 8}},
    )

    assert response.status_code == 409
    assert response.json()["diagnostic"]["fields"] == ["duration_seconds"]
    assert stored[("ready", "drama.json")]["scenes"][0]["duration_seconds"] == 6


def test_ad_shots_reject_stale_saves(scripts):
    client, stored = scripts
    stored[("ready", "ad.json")]["shots"][0]["voiceover_text"] = "别人刚改的口播"

    response = client.patch(
        "/api/v1/projects/ready/script-shots/S1",
        json={
            "script_file": "ad.json",
            "updates": {"voiceover_text": "我的口播"},
            "base": {"voiceover_text": "原来的口播"},
        },
    )

    assert response.status_code == 409
    assert stored[("ready", "ad.json")]["shots"][0]["voiceover_text"] == "别人刚改的口播"


@pytest.mark.parametrize("empty", [None, "", [], 0, False])
def test_a_field_missing_in_the_script_matches_an_empty_starting_point(scripts, empty):
    """编辑器把缺省字段显示成空值（空串、空列表、0、未勾选），以它为起点不算冲突。"""
    client, _stored = scripts

    response = client.patch(
        "/api/v1/projects/ready/segments/E1S01",
        json={"script_file": "narration.json", "note": "备注", "base": {"note": empty}},
    )

    assert response.status_code == 200
