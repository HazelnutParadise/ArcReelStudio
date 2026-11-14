"""当前 schema 的目标态依据摘要钉住不变。

规划器里有只服务 schema < 19 项目的口径分支（不记风格描述、记资产名、带转场的呈现依据、旧配音下限等），
迁移链不再接这些项目之后它们会被删掉或折成常量。下面的摘要由删分支之前的代码对当前 schema 项目规划一次
记下：删分支不得改动任何一条目标登记的产物路径或依据摘要，否则存量项目升级后会成片读作过期。
摘要只在规划口径确实有意改变时更新，并同时说明存量登记如何迁过去。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.artifacts.artifact_activation import plan_artifact_target_state
from lib.artifacts.artifact_manifest import ArtifactKey
from lib.project.project_manager import ProjectManager
from lib.project.project_migrations.runner import migrate_project_dir
from lib.project.project_schema import CURRENT_PROJECT_SCHEMA_VERSION
from lib.script.grid.models import GridGeneration, build_frame_chain
from lib.speech.narration_config import TtsSynthesisSettings
from server.services.presentation.presentation_read_model import PresentationReadModelService
from tests.integration.lib.artifacts.test_generation_input_parity import _project_dir as _ad_storyboard_project
from tests.legacy_project_shapes import write_legacy_storyboard_project, write_legacy_tts_narration_project

_GRID_ID = "grid_123456789abc"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _planned(project_dir: Path) -> dict[tuple[str, ...], tuple[str, str]]:
    project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    assert project["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION
    plan = plan_artifact_target_state(project_dir)
    return {_readable(key): (entry.artifact_path, entry.basis_digest) for key, entry in plan.entries.items()}


def _readable(key: ArtifactKey) -> tuple[str, ...]:
    return (key.kind.value, *(str(component) for component in key.components))


def _ad_storyboard_project_with_fixed_images(root: Path) -> Path:
    """The shared ad fixture encodes its PNGs with Pillow, whose output differs by platform; pin the bytes."""

    project_dir = _ad_storyboard_project(root, target_generated=True)
    images = (path for pattern in ("*.png", "*.jpg") for path in project_dir.rglob(pattern))
    for image in sorted(images):
        image.write_bytes(f"image:{image.relative_to(project_dir).as_posix()}".encode())
    return project_dir


def _grid_storyboard_project(root: Path) -> Path:
    """解说宫格项目，自定义风格带描述：宫格联合图、两张切格分镜图、一张单张分镜图与资产图，分镜图用 ``@`` 指认角色。"""

    project_dir = root / "grid"
    _write_json(
        project_dir / "project.json",
        {
            "schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
            "title": "宫格项目",
            "content_mode": "narration",
            "generation_mode": "storyboard",
            "source_language": "中文",
            "style": "写实电影感",
            "style_description": "淡彩",
            "aspect_ratio": "9:16",
            "grid_storyboard": True,
            "characters": {"阿离": {"description": "银发旅人", "character_sheet": "characters/阿离.png"}},
            "scenes": {"雨巷": {"description": "湿漉石板路", "scene_sheet": "scenes/雨巷.png"}},
            "props": {},
            "products": {},
            "episodes": [
                {
                    "episode": 1,
                    "title": "第一集",
                    "script_file": "scripts/episode_1.json",
                    "source_origin": "own",
                    "item_id_high_water": 3,
                }
            ],
            "narration_delivery": "post_production",
            "whole_source_files": [],
            "episode_id_high_water": 1,
            "source_remaining": False,
        },
    )
    members = ("E1S01", "E1S02")
    segments = [
        {
            "segment_id": resource_id,
            "episode": 1,
            "duration_seconds": 4,
            "novel_text": f"{resource_id} 的旁白。",
            "characters_in_segment": ["阿离"],
            "scenes": ["雨巷"],
            "props": [],
            "image_prompt": {"scene": f"@[阿离]站在{resource_id}的雨巷里", "composition": {"shot_type": "Medium Shot"}},
            "video_prompt": {"action": f"{resource_id} 的动作"},
            "generated_assets": {
                "storyboard_image": f"storyboards/scene_{resource_id}.png",
                "grid_id": _GRID_ID,
                "grid_cell_index": index,
            },
        }
        for index, resource_id in enumerate(members)
    ]
    segments.append(
        {
            "segment_id": "E1S03",
            "episode": 1,
            "duration_seconds": 4,
            "novel_text": "第三段旁白。",
            "segment_break": True,
            "characters_in_segment": ["阿离"],
            "scenes": [],
            "props": [],
            "image_prompt": {"scene": "@[阿离]在巷口回望", "composition": {"shot_type": "Wide Shot"}},
            "video_prompt": {"action": "回望"},
            "generated_assets": {"storyboard_image": "storyboards/scene_E1S03.png", "status": "completed"},
        }
    )
    _write_json(
        project_dir / "scripts" / "episode_1.json",
        {"episode": 1, "title": "第一集", "content_mode": "narration", "segments": segments},
    )
    _write_json(
        project_dir / "drafts" / "episode_1" / "script_plan_segments.json", {"segments": [{"novel_text": "雨夜"}]}
    )
    (project_dir / "source").mkdir()
    (project_dir / "source" / "episode_1.txt").write_text("雨夜", encoding="utf-8")
    grid = GridGeneration(
        id=_GRID_ID,
        episode=1,
        script_file="episode_1.json",
        scene_ids=list(members),
        grid_image_path=f"grids/{_GRID_ID}.png",
        rows=2,
        cols=2,
        cell_count=4,
        frame_chain=build_frame_chain(list(members), 2, 2),
        status="completed",
        prompt="grid",
        provider="provider",
        model="model",
        grid_size="grid_4",
        created_at="2026-01-01T00:00:00Z",
        split_at="2026-01-01T00:01:00Z",
        video_aspect_ratio="9:16",
    )
    grid_record = grid.to_dict()
    grid_record["reference_images"] = [{"path": "characters/阿离.png", "name": "阿离", "ref_type": "character"}]
    _write_json(project_dir / "grids" / f"{_GRID_ID}.json", grid_record)
    for rel, content in (
        (f"grids/{_GRID_ID}.png", b"composite"),
        *((f"storyboards/scene_{resource_id}.png", resource_id.encode()) for resource_id in (*members, "E1S03")),
        ("characters/阿离.png", b"character-sheet"),
        ("scenes/雨巷.png", b"scene-sheet"),
    ):
        (project_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (project_dir / rel).write_bytes(content)
    return project_dir


class _SettingsResolver:
    def __init__(self, settings: TtsSynthesisSettings) -> None:
        self.settings = settings

    async def resolve_tts_synthesis_settings(self, _project: dict) -> TtsSynthesisSettings:
        return self.settings


async def _presentation_project(root: Path) -> Path:
    """解说分镜项目从 v19 升级后物化一份后期配音的呈现模型与字幕草稿（分镜图、视频与剧本都已登记）。"""

    project_dir = write_legacy_storyboard_project(root / "projects", "presentation", unit_ids=("E1S1",))
    assert migrate_project_dir(project_dir) is True

    async def probe(_path: Path) -> float | None:
        return 4.0

    read_model = PresentationReadModelService(
        ProjectManager(root),
        settings_resolver_factory=lambda _name, _path: _SettingsResolver(
            TtsSynthesisSettings("openai", "tts-1", "alloy", 1.0)
        ),
        duration_probe=probe,
    )
    await read_model.materialize_unit(
        project_name="presentation", resource_type="videos", resource_id="E1S1", variant="post_production"
    )
    return project_dir


def _raised_tts_project(root: Path) -> Path:
    """TTS 配音项目从 v19 升级：旁白配音已登记，视频按旁白下限升档付费、时效时长仍是编排时长。"""

    project_dir = write_legacy_tts_narration_project(
        root / "projects",
        settings=(TtsSynthesisSettings("dashscope", "qwen3-tts-flash", "Cherry", None),),
        raised_video_duration_seconds=8,
    )
    assert migrate_project_dir(project_dir) is True
    return project_dir


_AD_STORYBOARD_DIGESTS: dict[tuple[str, ...], tuple[str, str]] = {
    ("asset-sheet", "character", "张三"): (
        "characters/张三.png",
        "sha256-v1:5e684101fc4a0522c241887e03449086d1315c8ce3d59244fd38fd7784f6e83a",
    ),
    ("asset-sheet", "character", "张三/劲装"): (
        "characters/derivatives/张三/劲装.png",
        "sha256-v1:4409c407c0a609998df75953ec66650b2493ea1c6548e9c83bcbd4a6158809c3",
    ),
    ("asset-sheet", "product", "保温杯"): (
        "products/保温杯.png",
        "sha256-v1:d3016e1d190e25587d4b8deb8e732250bc58f44852b483d1756d44be4d353da9",
    ),
    ("asset-sheet", "prop", "玉佩"): (
        "props/玉佩.png",
        "sha256-v1:43380f2f9ef9e695d2efbfd7f840bd6ac69222045ed253e55c7457db6c28876c",
    ),
    ("asset-sheet", "scene", "祠堂"): (
        "scenes/祠堂.png",
        "sha256-v1:6fd38a857e8291123b0d566b2135fc29437935797dfaa9fb38eec673fca4bad5",
    ),
    ("episode-storyboard", "1", "E1S01"): (
        "storyboards/scene_E1S01.png",
        "sha256-v1:a90ec015d21b4847d45d13f4e0287ae8995ca967bb5f45acac4b0b18700a7d61",
    ),
    ("episode-storyboard", "1", "E1S02"): (
        "storyboards/scene_E1S02.png",
        "sha256-v1:fa8b02d9ce53f77a4a6bac7271713c54ecba9469b75d8ebb84894b834dcfc9e4",
    ),
}
_GRID_STORYBOARD_DIGESTS: dict[tuple[str, ...], tuple[str, str]] = {
    ("asset-sheet", "character", "阿离"): (
        "characters/阿离.png",
        "sha256-v1:c965f752221fb36ba4b7d90378de3fbc0e073248cf0459a0dbeb95e3d5e28ee2",
    ),
    ("asset-sheet", "scene", "雨巷"): (
        "scenes/雨巷.png",
        "sha256-v1:5be0221e4906d075eb5710e65d5809f5ae4ee98045f1c587c5fd209f4ee5b704",
    ),
    ("episode-grid", "1", "grid_123456789abc"): (
        "grids/grid_123456789abc.png",
        "sha256-v1:6934fe6cfd566013274c9ba2f1ca7600393a7791e99d47afe2b24f268c460aca",
    ),
    ("episode-script", "1"): (
        "scripts/episode_1.json",
        "sha256-v1:491358f65d54863cc9473ffcbebc137bc5b1a8d930a431d21371c8ad2cc01f62",
    ),
    ("episode-script-plan", "1"): (
        "drafts/episode_1/script_plan_segments.json",
        "sha256-v1:dcf49f23b3c9527bdcc2713eccfd3bb0a499868ba8ea708204a36c62065e0ae4",
    ),
    ("episode-storyboard", "1", "E1S01"): (
        "storyboards/scene_E1S01.png",
        "sha256-v1:acb2a1918e0d6e4fff2cac2318d6fbebe7b7d2521ecb5c647abd388c57e61ab2",
    ),
    ("episode-storyboard", "1", "E1S02"): (
        "storyboards/scene_E1S02.png",
        "sha256-v1:7716a82d38075149f9a57d97b34e856e28b20650579d8b42ce48df6a8ed06684",
    ),
    ("episode-storyboard", "1", "E1S03"): (
        "storyboards/scene_E1S03.png",
        "sha256-v1:6bfc1d635fa63f16a371a19aef718174210a14181ebb870e6557f515ef8a956e",
    ),
}
_PRESENTATION_DIGESTS: dict[tuple[str, ...], tuple[str, str]] = {
    ("episode-presentation", "1", "E1S1", "post_production"): (
        "presentations/episode_1/RTFTMQ.post_production.json",
        "sha256-v1:5653d46b7723cb81758652cb1d01836bb45b0e17a72966212ac01e4ff73d5948",
    ),
    ("episode-script", "1"): (
        "scripts/episode_1.json",
        "sha256-v1:64a4c6c527fb0a9e643634ec73269a05ba8a4ee89b07910fb9bbc2b8d84ef12e",
    ),
    ("episode-storyboard", "1", "E1S1"): (
        "storyboards/scene_E1S1.png",
        "sha256-v1:0ddc19ee7cd130527f37e7ee2086bdfb8405945e73ffe8695e76716beca7ceb3",
    ),
    ("episode-subtitle", "1", "E1S1", "post_production"): (
        "subtitles/episode_1/RTFTMQ.post_production.json",
        "sha256-v1:b00e1399d1cea9b12075dd9ca4f4e2b72318796c320f0f60729f545a8da55931",
    ),
    ("episode-video", "1", "E1S1"): (
        "videos/scene_E1S1.mp4",
        "sha256-v1:5fb83c20911d2f7bd091d0aef46a2ae5ce2685216923a3e80d5f95fa9fa5ad79",
    ),
}
_RAISED_TTS_DIGESTS: dict[tuple[str, ...], tuple[str, str]] = {
    ("episode-audio", "1", "E1S1"): (
        "audio/segment_E1S1.wav",
        "sha256-v1:1145ed2273878afefbdfb4863f79bc15bfe5166b14d85733d50ba60065edaf46",
    ),
    ("episode-script", "1"): (
        "scripts/episode_1.json",
        "sha256-v1:64a4c6c527fb0a9e643634ec73269a05ba8a4ee89b07910fb9bbc2b8d84ef12e",
    ),
    ("episode-storyboard", "1", "E1S1"): (
        "storyboards/scene_E1S1.png",
        "sha256-v1:0ddc19ee7cd130527f37e7ee2086bdfb8405945e73ffe8695e76716beca7ceb3",
    ),
    ("episode-video", "1", "E1S1"): (
        "videos/scene_E1S1.mp4",
        "sha256-v1:5fb83c20911d2f7bd091d0aef46a2ae5ce2685216923a3e80d5f95fa9fa5ad79",
    ),
}


@pytest.mark.parametrize(
    ("make_project", "expected"),
    [
        pytest.param(
            _ad_storyboard_project_with_fixed_images,
            _AD_STORYBOARD_DIGESTS,
            id="ad-storyboards",
        ),
        pytest.param(_grid_storyboard_project, _GRID_STORYBOARD_DIGESTS, id="grid-and-split-storyboards"),
        pytest.param(_raised_tts_project, _RAISED_TTS_DIGESTS, id="tts-audio-and-raised-video"),
    ],
)
def test_the_target_state_of_a_current_project_keeps_its_basis_digests(tmp_path: Path, make_project, expected) -> None:
    assert _planned(make_project(tmp_path)) == expected


async def test_the_target_state_with_a_materialized_presentation_keeps_its_basis_digests(tmp_path: Path) -> None:
    assert _planned(await _presentation_project(tmp_path)) == _PRESENTATION_DIGESTS
