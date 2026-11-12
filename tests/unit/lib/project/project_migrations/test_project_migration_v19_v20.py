"""v19→v20 迁移：项目模型字段里只写了内置供应商的值，改写为 ``provider/目录推荐模型``（docs/adr/0130）。

推荐就是迁移这一刻目录里的推荐：迁移不读用户的启用状态，也不冻结任何升级前的版本。
音乐与音效没有推荐，它们的裸值原样保留；配音只用做得到文本转语音的推荐。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from lib.catalog import query as catalog
from lib.config.model_setting_keys import MODEL_SETTING_MEDIA_TYPES, PROJECT_MODEL_SETTING_KEYS
from lib.project.project_migrations import MIGRATORS
from lib.project.project_schema import CURRENT_PROJECT_SCHEMA_VERSION
from tests.catalog_support import install_catalog, with_recommendation

#: 与出厂快照不同的推荐：期望值只能来自「迁移这一刻目录的推荐」，不是写死的出厂默认。
ARK_VIDEO = "doubao-seedance-2-0-260128"
OPENAI_IMAGE = "gpt-image-2.5-flare"
GROK_TEXT = "grok-4.5"
DASHSCOPE_TTS = "qwen3-tts-flash"

_RECOMMENDED_PROVIDER = {"text": "grok", "image": "openai", "video": "ark", "audio": "dashscope"}
_RECOMMENDED_MODEL = {"text": GROK_TEXT, "image": OPENAI_IMAGE, "video": ARK_VIDEO, "audio": DASHSCOPE_TTS}


@pytest.fixture(autouse=True)
def recommendations(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = catalog.factory_snapshot()
    for provider_id, media_type, model in (
        ("ark", "video", ARK_VIDEO),
        ("openai", "image", OPENAI_IMAGE),
        ("grok", "text", GROK_TEXT),
    ):
        snapshot = with_recommendation(snapshot, provider_id, media_type, model)
    install_catalog(monkeypatch, snapshot)


def _write(tmp_path: Path, project: dict[str, Any]) -> Path:
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "project.json").write_text(json.dumps({"schema_version": 19, **project}), encoding="utf-8")
    return project_dir


def _load(project_dir: Path) -> dict[str, Any]:
    return json.loads((project_dir / "project.json").read_text(encoding="utf-8"))


def _migrate(tmp_path: Path, project: dict[str, Any]) -> dict[str, Any]:
    project_dir = _write(tmp_path, project)
    MIGRATORS[19](project_dir)
    return _load(project_dir)


def test_the_current_schema_is_20_and_the_chain_has_a_step_from_19() -> None:
    assert CURRENT_PROJECT_SCHEMA_VERSION == 20
    assert 19 in MIGRATORS


def test_bare_builtin_providers_take_the_catalog_recommendation(tmp_path: Path) -> None:
    migrated = _migrate(
        tmp_path,
        {
            "video_backend": "ark",
            "image_provider_t2i": "openai/",
            "text_backend_complex": " grok ",
            "audio_backend": "dashscope",
            "title": "ark",
        },
    )

    assert migrated == {
        "schema_version": 20,
        "video_backend": f"ark/{ARK_VIDEO}",
        "image_provider_t2i": f"openai/{OPENAI_IMAGE}",
        "text_backend_complex": f"grok/{GROK_TEXT}",
        "audio_backend": f"dashscope/{DASHSCOPE_TTS}",
        "title": "ark",
    }


@pytest.mark.parametrize(
    "key", [key for key in PROJECT_MODEL_SETTING_KEYS if key not in {"music_backend", "sfx_backend"}]
)
def test_every_text_image_video_and_narration_field_and_bucket_is_rewritten(tmp_path: Path, key: str) -> None:
    media_type = MODEL_SETTING_MEDIA_TYPES[key]

    migrated = _migrate(tmp_path, {key: _RECOMMENDED_PROVIDER[media_type]})

    assert migrated[key] == f"{_RECOMMENDED_PROVIDER[media_type]}/{_RECOMMENDED_MODEL[media_type]}"


@pytest.mark.parametrize(
    ("key", "provider_id"),
    [
        ("music_backend", "stability"),
        ("music_backend", "elevenlabs"),
        # 目录给了配音推荐的供应商写在音乐字段里也不补：音乐与音效没有推荐
        ("music_backend", "dashscope"),
        ("sfx_backend", "elevenlabs"),
        ("sfx_backend", "stability"),
        ("sfx_backend", "dashscope"),
    ],
)
def test_bare_music_and_sfx_values_are_kept_as_they_are(tmp_path: Path, key: str, provider_id: str) -> None:
    migrated = _migrate(tmp_path, {key: provider_id, "video_backend": "ark"})

    assert migrated[key] == provider_id
    assert migrated["video_backend"] == f"ark/{ARK_VIDEO}"


@pytest.mark.parametrize("provider_id", ["elevenlabs", "stability"])
def test_narration_keeps_a_bare_provider_whose_audio_recommendation_is_music(tmp_path: Path, provider_id: str) -> None:
    # 这两家的音频推荐是音乐模型，用它做旁白配音是错的，留给用户重新选
    assert catalog.default_model(provider_id, "audio") is not None

    assert _migrate(tmp_path, {"audio_backend": provider_id})["audio_backend"] == provider_id


def test_values_that_are_not_bare_builtin_providers_or_have_no_recommendation_stay(tmp_path: Path) -> None:
    project = {
        # openai 没有视频推荐：原样保留，运行时报没有选定模型，由用户重新选择
        "video_provider_r2v": "openai",
        # 自定义供应商的裸 id、不认识的供应商
        "text_backend_simple": "custom-3",
        "video_provider_i2v": "no-such-provider",
        "default_image_backend": "openai/gpt-image-2",
        "image_provider_i2i": "openai/gpt-image-2.5-sunburst",
        "default_text_backend": 3,
        "text_backend_complex": "",
        "video_backend": None,
    }

    assert _migrate(tmp_path, project) == {**project, "schema_version": 20}


def test_a_recommendation_the_catalog_no_longer_gives_leaves_the_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_catalog(monkeypatch, with_recommendation(catalog.factory_snapshot(), "ark", "video", None))

    assert _migrate(tmp_path, {"video_backend": "ark"})["video_backend"] == "ark"


def test_connection_side_keys_are_not_touched(tmp_path: Path) -> None:
    project = {
        "video_backend": "ark",
        "video_backend_credential_id": 7,
        "text_backend_complex": "grok",
        "text_backend_complex_credential_id": None,
        "audio_backend": "dashscope",
        "audio_backend_credential_id": "3",
    }

    migrated = _migrate(tmp_path, project)

    assert {key: value for key, value in migrated.items() if key.endswith("_credential_id")} == {
        key: value for key, value in project.items() if key.endswith("_credential_id")
    }
    assert migrated["video_backend"] == f"ark/{ARK_VIDEO}"


def test_the_step_does_not_move_the_last_activity_time(tmp_path: Path) -> None:
    metadata = {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T03:04:05Z"}

    assert _migrate(tmp_path, {"video_backend": "ark", "metadata": metadata})["metadata"] == metadata


def test_rerunning_the_step_is_a_noop(tmp_path: Path) -> None:
    project_dir = _write(tmp_path, {"video_backend": "ark"})
    MIGRATORS[19](project_dir)
    once = (project_dir / "project.json").read_bytes()

    MIGRATORS[19](project_dir)

    assert (project_dir / "project.json").read_bytes() == once


def test_a_project_already_at_v20_keeps_its_bare_values(tmp_path: Path) -> None:
    project_dir = _write(tmp_path, {"schema_version": 20, "video_backend": "ark"})
    before = (project_dir / "project.json").read_bytes()

    MIGRATORS[19](project_dir)

    assert (project_dir / "project.json").read_bytes() == before


def test_project_json_is_written_once_through_an_atomic_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = _write(
        tmp_path, {"video_backend": "ark", "text_backend_complex": "grok", "audio_backend": "dashscope"}
    )
    replaced: list[str] = []
    real_replace = os.replace

    def recording_replace(src: Any, dst: Any) -> None:
        replaced.append(Path(dst).name)
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", recording_replace)

    MIGRATORS[19](project_dir)

    assert replaced == ["project.json"]
    assert _load(project_dir)["schema_version"] == 20


def test_a_failed_write_leaves_the_old_file_for_the_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir = _write(tmp_path, {"video_backend": "ark"})
    before = (project_dir / "project.json").read_bytes()

    def failing_replace(src: Any, dst: Any) -> None:
        raise OSError("disk full")

    # 只撤掉这一处替身：monkeypatch.undo() 会连同装入的测试目录一起撤掉
    with monkeypatch.context() as patched:
        patched.setattr(os, "replace", failing_replace)
        with pytest.raises(OSError, match="disk full"):
            MIGRATORS[19](project_dir)

    assert (project_dir / "project.json").read_bytes() == before
    assert not list(project_dir.glob("*.tmp"))

    MIGRATORS[19](project_dir)
    assert _load(project_dir)["video_backend"] == f"ark/{ARK_VIDEO}"
