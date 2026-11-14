"""迁移链接得住的最早版本（schema 19）写出的项目，以及这一版代码仍可能留下、要由链首规整接住的旧形态。

迁移链只接 schema 19 与 20，更早的项目在规整与备份之前就被拒绝。样本直接按当前形态写成 schema 19 的项目：
文件按当前代码的形态写，产物清单由当前规划器整份激活登记（:func:`activate_at_schema_19` 先标成当前版本
激活，再标回 19），样本要表现的旧形态叠在这之后。形态清单见 ``docs/agents/project-migrations.md``「已知旧形态」。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.artifacts.artifact_manifest import (
    ArtifactBasis,
    ArtifactBasisDescriptor,
    ArtifactKey,
    ArtifactManifest,
    ProjectArtifactManifestAdapter,
    compose_video_artifact_basis,
)
from lib.artifacts.artifact_version_provenance import VIDEO_CURRENCY_DURATION_FIELD
from lib.artifacts.version_manager import VERSION_CONTENT_DIGEST, VersionManager
from lib.artifacts.video_artifact_facts import VideoArtifactCurrencyFacts
from lib.artifacts.visual_artifact_provenance import build_storyboard_video_artifact_visual_basis
from lib.script.script_review import content_fingerprint
from lib.speech.narration_config import TtsSynthesisSettings, tts_snapshot_fields
from lib.speech.narration_delivery import build_narration_audio_basis
from lib.speech.speech_artifact_provenance import build_video_duration_basis, build_video_speech_basis
from lib.speech.speech_composition import admit_script_unit
from tests.factories import activate_current_project

#: 迁移链接得住的最早版本。
SCHEMA_V19 = 19

_CONFIRMED_AT = "2026-10-20T00:00:00Z"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json_object(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ledger_entry(project: dict[str, Any], episode: int) -> dict[str, Any]:
    return next(entry for entry in project["episodes"] if entry["episode"] == episode)


def _set_schema_version(project_dir: Path, version: int) -> None:
    project_path = project_dir / "project.json"
    project = _load_json_object(project_path)
    project["schema_version"] = version
    _write_json(project_path, project)


def activate_at_schema_19(project_dir: Path) -> None:
    """按当前规划器整份登记在场产物，再把项目标回 schema 19：v19 发行版的清单与当前规划口径一致。"""

    activate_current_project(project_dir)
    _set_schema_version(project_dir, SCHEMA_V19)


def _v19_project(**fields: Any) -> dict[str, Any]:
    """schema 19 的 ``project.json`` 骨架：v19 发行版新建与升级后都带的字段齐全，``fields`` 覆盖缺省值。"""

    project: dict[str, Any] = {
        "schema_version": SCHEMA_V19,
        "title": "v19 项目",
        "content_mode": "narration",
        "generation_mode": "storyboard",
        "source_language": "中文",
        "style": "写实",
        "style_description": "电影感",
        "aspect_ratio": "9:16",
        "grid_storyboard": False,
        "characters": {},
        "scenes": {},
        "props": {},
        "products": {},
        "episodes": [],
        "character_voice_binding": "prompt",
        "narration_delivery": "post_production",
        "whole_source_files": [],
        "episode_id_high_water": 0,
        "source_remaining": False,
    }
    project.update(fields)
    return project


def write_v19_project(root: Path, name: str = "demo", *, activate: bool = True) -> Path:
    """解说分镜项目：四类资产图、一集剧本（一个已出分镜图的分镜）、已确认的脚本规划与分集原文。

    ``activate=False`` 时不登记产物清单，调用方叠完旧形态后自行调用 :func:`activate_at_schema_19`。
    """

    project_dir = root / name
    project_dir.mkdir(parents=True)
    script_plan = {"segments": [{"novel_text": "雨夜"}]}
    plan_path = project_dir / "drafts" / "episode_1" / "script_plan_segments.json"
    _write_json(plan_path, script_plan)
    _write_json(
        project_dir / "project.json",
        _v19_project(
            title="v19 解说项目",
            style="水墨",
            style_description="淡彩",
            characters={
                "阿离": {"description": "银发旅人", "character_sheet": "characters/阿离.png", "derivatives": {}}
            },
            scenes={"雨巷": {"description": "湿漉石板路", "scene_sheet": "scenes/雨巷.png"}},
            props={"伞": {"description": "油纸伞", "prop_sheet": "props/伞.png"}},
            products={
                "咖啡": {
                    "description": "玻璃瓶咖啡",
                    "product_sheet": "products/咖啡.png",
                    "reference_images": ["products/refs/咖啡.png"],
                }
            },
            episodes=[
                {
                    "episode": 1,
                    "title": "第一集",
                    "script_file": "scripts/episode_1.json",
                    "script_plan_review": {
                        "fingerprint": content_fingerprint(plan_path),
                        "confirmed_at": _CONFIRMED_AT,
                    },
                    "source_origin": "own",
                    "item_id_high_water": 1,
                }
            ],
            episode_id_high_water=1,
        ),
    )
    _write_json(
        project_dir / "scripts" / "episode_1.json",
        {
            "episode": 1,
            "title": "第一集",
            "content_mode": "narration",
            "segments": [
                {
                    "segment_id": "E1S01",
                    "novel_text": "雨夜",
                    "image_prompt": "阿离站在雨中",
                    "video_prompt": "阿离转身",
                    "characters_in_segment": [],
                    "scenes": [],
                    "props": [],
                    "generated_assets": {"storyboard_image": "storyboards/scene_E1S01.png"},
                }
            ],
        },
    )
    (project_dir / "source").mkdir()
    (project_dir / "source" / "episode_1.txt").write_text("雨夜", encoding="utf-8")
    for rel, content in (
        ("characters/阿离.png", b"character"),
        ("scenes/雨巷.png", b"scene"),
        ("props/伞.png", b"prop"),
        ("products/咖啡.png", b"product"),
        ("products/refs/咖啡.png", b"original"),
        ("storyboards/scene_E1S01.png", b"storyboard"),
    ):
        (project_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (project_dir / rel).write_bytes(content)
    if activate:
        activate_at_schema_19(project_dir)
    return project_dir


def _add_typed_storyboard_video(
    project_dir: Path,
    segment: dict[str, Any],
    *,
    episode: int = 1,
    execution_duration_seconds: int | None = None,
) -> None:
    """给分镜写一段视频与一条选中的类型化版本记录，取证依据按当前代码算（v19 的视频记录都带它）。

    ``execution_duration_seconds`` 大于编排时长时，记录是 TTS 下限升档后的付费事实：申请与档位按升档值记，
    时效依据仍只以编排时长为时长输入。
    """

    unit_id = segment["segment_id"]
    storyboard = project_dir / segment["generated_assets"]["storyboard_image"]
    video = project_dir / "videos" / f"scene_{unit_id}.mp4"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(f"provider-video-{unit_id}".encode())
    planned = segment["duration_seconds"]
    paid = execution_duration_seconds or planned
    visual = build_storyboard_video_artifact_visual_basis(
        resource_id=unit_id,
        visual_prompt=segment["video_prompt"],
        storyboard_image=storyboard,
        end_frame_image=None,
        aspect_ratio="9:16",
    )
    speech = build_video_speech_basis(admit_script_unit("segments", segment).preparation)
    duration = build_video_duration_basis(paid)
    facts = VideoArtifactCurrencyFacts(
        episode=episode,
        request_duration_seconds=paid,
        visual_basis=visual,
        speech_basis=speech,
        duration_basis=duration,
        video_basis=compose_video_artifact_basis(visual=visual, speech=speech, duration=duration),
        voice_style_speakers=(),
        duration_tiers=tuple(sorted({planned, paid})),
        reference_image_limit=None,
        parent_version=0,
    )
    extra: dict[str, Any] = {}
    if paid != planned:
        extra = {
            "duration_seconds": paid,
            "execution_narration": {"delivery": "use_tts"},
            VIDEO_CURRENCY_DURATION_FIELD: planned,
        }
    VersionManager(project_dir).add_version(
        "videos",
        unit_id,
        f"{unit_id} 的视频",
        source_file=video,
        execution_checkpoint_schema_version=3,
        execution_duration_seconds=paid,
        execution_request_digest="a" * 64,
        execution_script_file=f"episode_{episode}.json",
        execution_provider_media=[],
        execution_generate_audio=False,
        artifact_video_currency=facts.to_dict(),
        **extra,
    )


def write_legacy_storyboard_project(
    root: Path,
    name: str = "legacy-storyboard",
    *,
    unit_ids: tuple[str, ...] = ("E1S1", "E1S2"),
    activate: bool = True,
) -> Path:
    """解说分镜项目：分镜图与视频齐全，视频各有一条选中的类型化版本记录。

    源文是上传原名的整本源文（``source/1-7-0227.txt``），脚本规划草稿是 ``.md``（≤ 0.26 留下的形态，v19 照常带着）。
    ``activate=False`` 时不登记产物清单。
    """

    project_dir = root / name
    project_dir.mkdir(parents=True)
    _write_json(
        project_dir / "project.json",
        _v19_project(
            title="旧项目",
            episodes=[
                {
                    "episode": 1,
                    "title": "第一集",
                    "script_file": "scripts/episode_1.json",
                    "source_origin": "none",
                    "item_id_high_water": len(unit_ids),
                }
            ],
            whole_source_files=[{"source_file": "source/1-7-0227.txt"}],
            episode_id_high_water=1,
            source_remaining=True,
        ),
    )
    segments = [
        {
            "segment_id": unit_id,
            "episode": 1,
            "duration_seconds": 4,
            "novel_text": f"第{index}段旁白。",
            "characters_in_segment": [],
            "scenes": [],
            "props": [],
            "image_prompt": {"scene": f"画面 {index}"},
            "video_prompt": {"action": f"动作 {index}", "camera_motion": "Pan Right"},
            "generated_assets": {
                "storyboard_image": f"storyboards/scene_{unit_id}.png",
                "video_clip": f"videos/scene_{unit_id}.mp4",
                "status": "completed",
            },
        }
        for index, unit_id in enumerate(unit_ids, start=1)
    ]
    _write_json(
        project_dir / "scripts" / "episode_1.json",
        {"episode": 1, "title": "第一集", "content_mode": "narration", "segments": segments},
    )
    (project_dir / "source").mkdir()
    (project_dir / "source" / "1-7-0227.txt").write_text("第一段旁白。第二段旁白。", encoding="utf-8")
    drafts = project_dir / "drafts" / "episode_1"
    drafts.mkdir(parents=True)
    (drafts / "script_plan_segments.md").write_text("# 分段\n\n1. 第一段旁白。\n2. 第二段旁白。\n", encoding="utf-8")
    (project_dir / "storyboards").mkdir()
    for segment in segments:
        unit_id = segment["segment_id"]
        (project_dir / "storyboards" / f"scene_{unit_id}.png").write_bytes(f"storyboard-{unit_id}".encode())
        _add_typed_storyboard_video(project_dir, segment)
    if activate:
        activate_at_schema_19(project_dir)
    return project_dir


def write_legacy_bare_provider_project(root: Path) -> Path:
    """项目模型字段只写了内置供应商、没写模型（schema 19 的运行时按目录默认模型补全，现在目录默认只作推荐）。

    会被改写的：视频默认写裸 ``ark``，图片文生图桶是缺模型的脏值 ``openai/``，复杂档文本两端带空白（``" grok "``），
    默认文本模型是裸 ``grok``（旁边带连线旁键），配音写裸 ``dashscope``。
    原样保留的：视频参考生桶写没有视频推荐的 ``openai``，简单档文本写自定义供应商的裸 id，图片默认是完整的
    ``provider/model``，音乐与音效写裸供应商（音乐与音效没有推荐）。``metadata.updated_at`` 记着最近活动时间。
    """

    project_dir = write_legacy_storyboard_project(root, name="legacy-bare-provider-v19")
    project_path = project_dir / "project.json"
    project = _load_json_object(project_path)
    project.update(
        {
            "video_backend": "ark",
            "image_provider_t2i": "openai/",
            "text_backend_complex": " grok ",
            "default_text_backend": "grok",
            "default_text_backend_credential_id": 4,
            "audio_backend": "dashscope",
            "video_provider_r2v": "openai",
            "text_backend_simple": "custom-3",
            "default_image_backend": "openai/gpt-image-2",
            "music_backend": "stability",
            "sfx_backend": "elevenlabs",
            "metadata": {"created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T03:04:05Z"},
        }
    )
    _write_json(project_path, project)
    return project_dir


def write_legacy_timeline_project(root: Path) -> Path:
    """在 :func:`write_legacy_storyboard_project` 上加一条剪辑时间线（新建与编辑各一个修订）。"""

    project_dir = write_legacy_storyboard_project(root, name="legacy-timeline")
    clip = {"id": "c1", "unit_id": "E1S1", "source_volume": 1.0}
    _write_json(
        project_dir / "edit_timelines" / "episode_1" / "tl-0000abcd.json",
        {
            "schema_version": 1,
            "id": "tl-0000abcd",
            "episode": 1,
            "name": "初剪",
            "created_at": "2026-09-01T00:00:00Z",
            "next_clip_number": 2,
            "revisions": [
                {
                    "number": 1,
                    "author": {"kind": "arcreel_agent"},
                    "summary": "按脚本新建",
                    "created_at": "2026-09-01T00:00:00Z",
                    "content": {"clips": [clip]},
                },
                {
                    "number": 2,
                    "parent": 1,
                    "author": {"kind": "creator", "user_id": "u1"},
                    "summary": "调整音量",
                    "created_at": "2026-09-02T00:00:00Z",
                    "content": {"clips": [{**clip, "source_volume": 0.6}]},
                    "changed_clip_ids": ["c1"],
                },
            ],
        },
    )
    return project_dir


def write_legacy_tts_narration_project(
    root: Path,
    name: str = "legacy-tts-narration",
    *,
    settings: tuple[TtsSynthesisSettings, ...] = (
        TtsSynthesisSettings("dashscope", "qwen3-tts-flash", "Cherry", None),
        TtsSynthesisSettings("dashscope", "qwen3-tts-flash", "Ethan", 1.2),
    ),
    with_tts_settings: bool = True,
    raised_video_duration_seconds: int | None = None,
) -> Path:
    """解说分镜项目带旁白配音：每个分镜一条选中的音频版本，第 i 个分镜的旁白用 ``settings[i]`` 合成。

    ``with_tts_settings=True`` 是 TTS 配音项目：版本记录带完整 TTS 设置与配音依据，``project.json`` 记旁白交付方式
    ``use_tts`` 与最新一条的设置。``with_tts_settings=False`` 是更早版本留下、v19 仍带着的旁白记录：没有 TTS 设置，
    也没有配音依据，项目是后期配音。

    ``raised_video_duration_seconds`` 非空时视频按旁白下限升档付费，编排仍为 4 秒：选中的视频记录按升档值记
    申请与档位，时效时长记编排时长。
    """

    unit_ids = tuple(f"E1S{index}" for index in range(1, len(settings) + 1))
    project_dir = write_legacy_storyboard_project(root, name, unit_ids=unit_ids, activate=False)
    script_path = project_dir / "scripts" / "episode_1.json"
    script = _load_json_object(script_path)
    versions = VersionManager(project_dir)
    metadata_path = project_dir / "versions" / "versions.json"
    for index, (segment, synthesis) in enumerate(zip(script["segments"], settings, strict=True), start=1):
        unit_id = segment["segment_id"]
        audio_path = f"audio/segment_{unit_id}.wav"
        segment["generated_assets"]["narration_audio"] = audio_path
        audio = project_dir / audio_path
        audio.parent.mkdir(exist_ok=True)
        audio.write_bytes(f"tts-{unit_id}".encode())
        if with_tts_settings:
            basis = ArtifactBasisDescriptor.from_basis(
                build_narration_audio_basis(admit_script_unit("segments", segment).preparation, synthesis)
            )
            versions.add_version(
                "audio",
                unit_id,
                segment["novel_text"],
                source_file=audio,
                artifact_episode=1,
                artifact_audio_basis=basis.to_dict(),
                execution_script_file="episode_1.json",
                tts_actual_duration_seconds=(
                    3.0 if raised_video_duration_seconds is None else raised_video_duration_seconds - 2.0
                ),
                tts_provider_id=synthesis.provider_id,
                tts_model_id=synthesis.model_id,
                tts_voice=synthesis.voice,
                tts_speed=synthesis.speed,
                tts_basis_digest=basis.digest,
            )
        else:
            versions.add_version("audio", unit_id, segment["novel_text"], source_file=audio)
        metadata = _load_json_object(metadata_path)
        metadata["audio"][unit_id]["versions"][-1]["created_at"] = f"2026-04-0{index}T10:00:00Z"
        if not with_tts_settings:
            metadata["audio"][unit_id]["versions"][-1].pop(VERSION_CONTENT_DIGEST, None)
        _write_json(metadata_path, metadata)
    _write_json(script_path, script)
    if raised_video_duration_seconds is not None:
        metadata = _load_json_object(metadata_path)
        for unit_id in unit_ids:
            metadata["videos"].pop(unit_id)
        _write_json(metadata_path, metadata)
        for segment in script["segments"]:
            _add_typed_storyboard_video(project_dir, segment, execution_duration_seconds=raised_video_duration_seconds)
    if with_tts_settings:
        project_path = project_dir / "project.json"
        project = _load_json_object(project_path)
        project.update(tts_snapshot_fields(settings[-1]), narration_delivery="use_tts")
        _write_json(project_path, project)
    activate_at_schema_19(project_dir)
    return project_dir


def write_legacy_drama_storyboard_project(root: Path, name: str = "legacy-drama-storyboard") -> Path:
    """剧情演绎项目，``project.json`` 没有 ``aspect_ratio`` 字段（很早期版本或导入项目留下）；首条分镜已有分镜图。"""

    project_dir = root / name
    project_dir.mkdir(parents=True)
    project = _v19_project(
        title="旧剧情项目",
        content_mode="drama",
        default_duration=8,
        episodes=[
            {
                "episode": 1,
                "title": "第1集",
                "script_file": "scripts/episode_1.json",
                "source_origin": "own",
                "item_id_high_water": 2,
            }
        ],
        episode_id_high_water=1,
    )
    project.pop("aspect_ratio")
    _write_json(project_dir / "project.json", project)
    scenes = [
        {
            "scene_id": f"E1S0{index}",
            "duration_seconds": 8,
            "segment_break": False,
            "characters_in_scene": [],
            "scenes": [],
            "props": [],
            "utterances": [{"kind": "voiceover", "speaker": None, "text": f"第{index}句旁白。"}],
            "source_text": f"第{index}段原文。",
            "scene_description": f"第{index}镜的视觉改编。",
            "image_prompt": {"scene": "画面", "composition": {"shot_type": "Medium Shot"}},
            "video_prompt": {"action": "动作"},
        }
        for index in (1, 2)
    ]
    scenes[0]["generated_assets"] = {"storyboard_image": "storyboards/scene_E1S01.png", "status": "completed"}
    _write_json(
        project_dir / "scripts" / "episode_1.json",
        {"episode": 1, "title": "第1集", "content_mode": "drama", "scenes": scenes},
    )
    (project_dir / "source").mkdir()
    (project_dir / "source" / "episode_1.txt").write_text("第1集原文。", encoding="utf-8")
    (project_dir / "storyboards").mkdir()
    (project_dir / "storyboards" / "scene_E1S01.png").write_bytes(b"storyboard-E1S01")
    activate_at_schema_19(project_dir)
    return project_dir


def write_legacy_shared_reference_project(root: Path) -> Path:
    """跨资产共用参考文件：角色 Alice 与 Bob 共用 Alice 名下的参考图与参考音频，商品「咖啡」也引用那张图。

    项目没有生成过产物，也就没有产物清单。
    """

    project_dir = root / "demo"
    image, audio = "characters/refs/Alice.png", "characters/refs_audio/Alice.wav"
    _write_json(
        project_dir / "project.json",
        _v19_project(
            title="共用参考文件项目",
            characters={
                "Alice": {"description": "owner", "reference_image": image, "reference_audio": audio},
                "Bob": {"description": "borrower", "reference_image": image, "reference_audio": audio},
            },
            products={"咖啡": {"description": "product", "reference_images": [image]}},
        ),
    )
    for rel, content in ((image, b"image"), (audio, b"audio")):
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return project_dir


def set_script_episode(project_dir: Path, episode: int, value: int | None) -> None:
    """同步与保存都接受顶层不写集号、或集号与绑定不符的剧本；``None`` 表示删去该字段。"""

    project = _load_json_object(project_dir / "project.json")
    script_path = project_dir / _ledger_entry(project, episode)["script_file"]
    script = _load_json_object(script_path)
    if value is None:
        script.pop("episode", None)
    else:
        script["episode"] = value
    _write_json(script_path, script)


def add_colliding_asset_name(project_dir: Path, bucket: str, name: str) -> str:
    """资产名比对坐标系（去两端空白、Unicode NFC）之外的写入路径可登记出归一后同名的两条资产。

    在 ``bucket`` 里加一条与 ``name`` 只差尾随空格的资产，返回新名字。
    """

    project_path = project_dir / "project.json"
    project = _load_json_object(project_path)
    colliding = f"{name} "
    project[bucket][colliding] = {"description": "同名的另一份"}
    _write_json(project_path, project)
    return colliding


def add_asset_names_differing_only_in_case(project_dir: Path, bucket: str, sheet_field: str, name: str) -> str:
    """同一资产表可登记出只差大小写的两条资产。

    在 ``bucket`` 末尾加 ``name`` 与它的全大写变体，各带一张资产图（不区分大小写的文件系统上两张图
    落到同一个文件），返回变体名。
    """

    project_path = project_dir / "project.json"
    project = _load_json_object(project_path)
    variant = name.upper()
    for asset_name, content in ((name, b"original"), (variant, b"variant")):
        sheet = f"{bucket}/{asset_name}.png"
        project[bucket][asset_name] = {"description": f"{asset_name} 的描述", sheet_field: sheet}
        (project_dir / sheet).parent.mkdir(parents=True, exist_ok=True)
        (project_dir / sheet).write_bytes(content)
    _write_json(project_path, project)
    return variant


def add_asset_names_differing_only_in_whitespace(
    project_dir: Path, bucket: str, sheet_field: str, name: str, *, variant_sheet: str | None = None
) -> str:
    """同一资产表可登记出只差尾随空格的两条资产，两者共用一个产物清单键。

    在 ``bucket`` 末尾加 ``name`` 与它带尾随空格的变体，各带一张资产图（变体的图落在规范路径上）；变体的资产图字段
    写 ``variant_sheet``（旧版 PATCH 原样收下的写法，如 ``./`` 前缀或反斜杠），缺省为规范写法。返回变体名。
    """

    project_path = project_dir / "project.json"
    project = _load_json_object(project_path)
    variant = f"{name} "
    for asset_name, content in ((name, b"kept"), (variant, b"variant")):
        sheet = f"{bucket}/{asset_name}.png"
        declared = variant_sheet if asset_name == variant and variant_sheet is not None else sheet
        project[bucket][asset_name] = {"description": f"{asset_name} 的描述", sheet_field: declared}
        (project_dir / sheet).parent.mkdir(parents=True, exist_ok=True)
        (project_dir / sheet).write_bytes(content)
    _write_json(project_path, project)
    return variant


def share_reference_files(project_dir: Path) -> dict[str, bytes]:
    """旧版资产 PATCH 接受任意路径，参考图与参考音频可以指向别的资产名下的文件。

    角色「阿离」带自己名下的参考图与参考音频，新加的角色「阿青」两个字段都指着这两份；「阿青」名下另有
    一张没被引用的参考图。商品「咖啡」带第 1 张原图，新加的商品「茶」的原图列表指着它。返回各份文件的内容。
    """

    project_path = project_dir / "project.json"
    project = _load_json_object(project_path)
    contents = {
        "characters/refs/阿离.png": b"ali-image",
        "characters/refs_audio/阿离.wav": b"ali-voice",
        "characters/refs/阿青.png": b"qing-stray",
        "products/refs/咖啡_1.png": b"coffee-1",
    }
    for rel, content in contents.items():
        (project_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (project_dir / rel).write_bytes(content)
    shared = {"reference_image": "characters/refs/阿离.png", "reference_audio": "characters/refs_audio/阿离.wav"}
    project["characters"]["阿离"].update(shared)
    project["characters"]["阿青"] = {"description": "青衣少年", "character_sheet": "", **shared}
    project["products"]["咖啡"]["reference_images"] = ["products/refs/咖啡_1.png"]
    project["products"]["茶"] = {
        "description": "冷泡茶",
        "product_sheet": "",
        "reference_images": ["products/refs/咖啡_1.png"],
    }
    _write_json(project_path, project)
    return contents


def share_asset_sheets(project_dir: Path) -> dict[str, bytes]:
    """旧版资产 PATCH 接受任意路径，资产图字段也可以指向别的资产名下的图。

    角色「阿离」带自己名下的参考图，新加的角色「阿青」的资产图指着它，「阿青」名下另有一张没被引用的资产图。
    在产物清单激活之前写下时，激活按这个共用的路径登记「阿青」的资产图（同一路径没有别的登记）。
    返回参考图的内容（样本取 :func:`write_v19_project` 一类带角色「阿离」的项目）。
    """

    project_path = project_dir / "project.json"
    project = _load_json_object(project_path)
    reference = "characters/refs/阿离.png"
    (project_dir / reference).parent.mkdir(parents=True, exist_ok=True)
    (project_dir / reference).write_bytes(b"ali-image")
    (project_dir / "characters/阿青.png").write_bytes(b"qing-stray")
    project["characters"]["阿离"]["reference_image"] = reference
    project["characters"]["阿青"] = {"description": "青衣少年", "character_sheet": reference}
    _write_json(project_path, project)
    return {reference: b"ali-image"}


def share_derivative_sheet(project_dir: Path) -> str:
    """旧版 PATCH 允许本体资产图指向另一个资产的衍生图。"""

    project_path = project_dir / "project.json"
    project = _load_json_object(project_path)
    derivative = "characters/derivatives/阿离/雨衣.png"
    project["characters"]["阿离"]["derivatives"] = {"雨衣": {"description": "穿雨衣", "character_sheet": derivative}}
    project["characters"]["阿青"] = {"description": "青衣少年", "character_sheet": derivative}
    _write_json(project_path, project)
    (project_dir / derivative).parent.mkdir(parents=True, exist_ok=True)
    (project_dir / derivative).write_bytes(b"raincoat")
    return derivative


def repoint_registered_asset_sheet(project_dir: Path) -> dict[str, bytes]:
    """资产图登记之后才经 PATCH 改指别的资产名下的图：场景「雨巷」的资产图改指道具「伞」的资产图。

    「雨巷」自己的图与登记留在原处，登记因路径对不上读作缺失；两个条目声明同一张图，改指前的规划器拒绝整个项目。
    返回两张图改指前的内容（样本取带场景「雨巷」与道具「伞」、已有清单登记的项目）。
    """

    project_path = project_dir / "project.json"
    project = _load_json_object(project_path)
    contents = {rel: (project_dir / rel).read_bytes() for rel in ("scenes/雨巷.png", "props/伞.png")}
    project["scenes"]["雨巷"]["scene_sheet"] = "props/伞.png"
    _write_json(project_path, project)
    return contents


def refer_to_asset_in_episode(project_dir: Path, episode: int, field: str, name: str) -> None:
    """只差大小写的两条资产并存时，剧本与草稿可以写其中任何一个的名字。

    让该集剧本第一个分镜在引用数组 ``field`` 与画面描述的 ``@`` 提及里写 ``name``，脚本规划草稿
    第一段的同一引用数组也写它（剧本形态取 :func:`write_v19_project` 一类的解说分镜）。
    """

    project = _load_json_object(project_dir / "project.json")
    script_path = project_dir / _ledger_entry(project, episode)["script_file"]
    script = _load_json_object(script_path)
    segment = script["segments"][0]
    segment.setdefault(field, []).append(name)
    segment["image_prompt"] = f"@[{name}]{segment.get('image_prompt') or ''}"
    _write_json(script_path, script)
    draft_path = project_dir / "drafts" / f"episode_{episode}" / "script_plan_segments.json"
    draft = _load_json_object(draft_path)
    draft["segments"][0].setdefault(field, []).append(name)
    _write_json(draft_path, draft)


def break_script_item_ids(project_dir: Path, episode: int) -> None:
    """降级保存的剧本可以有重复或缺失的条目 id。

    在第一个条目后追加一条同 id 的条目（提示词不同）与一条没有 id、没有产物的条目。
    """

    project = _load_json_object(project_dir / "project.json")
    script_path = project_dir / _ledger_entry(project, episode)["script_file"]
    script = _load_json_object(script_path)
    kind = next(key for key in ("segments", "scenes", "shots", "video_units") if key in script)
    id_field = {"segments": "segment_id", "scenes": "scene_id", "shots": "shot_id", "video_units": "unit_id"}[kind]
    first = script[kind][0]
    duplicate = {**first, "image_prompt": "另一镜"}
    missing = {key: value for key, value in first.items() if key != id_field}
    missing["generated_assets"] = {}
    script[kind] = [first, duplicate, missing]
    _write_json(script_path, script)


def reuse_item_id_across_episodes(project_dir: Path, item_id: str) -> None:
    """剧本 id 只在本集内判重时，复制来的剧本可以和另一集有同号条目，两边认领同一个媒体文件。

    账本里新登记第 2 集，剧本复制自第 1 集；两集首个条目都改成 ``item_id``，分镜图引用指向它的规范路径，
    盘上放一张该路径的分镜图。
    """

    project_path = project_dir / "project.json"
    project = _load_json_object(project_path)
    first_path = project_dir / _ledger_entry(project, 1)["script_file"]
    first = _load_json_object(first_path)
    second = {**json.loads(json.dumps(first)), "episode": 2, "title": "第2集"}
    for script in (first, second):
        segment = script["segments"][0]
        segment["segment_id"] = item_id
        segment["generated_assets"]["storyboard_image"] = f"storyboards/scene_{item_id}.png"
    _write_json(first_path, first)
    _write_json(project_dir / "scripts" / "episode_2.json", second)
    (project_dir / "storyboards").mkdir(exist_ok=True)
    (project_dir / "storyboards" / f"scene_{item_id}.png").write_bytes(b"shared storyboard")
    project["episodes"].append(
        {"episode": 2, "title": "第2集", "script_file": "scripts/episode_2.json", "source_origin": "none"}
    )
    project["episode_id_high_water"] = 2
    _write_json(project_path, project)


def drop_selected_version_snapshot(project_dir: Path, resource_type: str, resource_id: str) -> str:
    """手工打包或清理过版本目录的项目里，选中版本记录还在、它的快照文件已不在；返回被删掉的快照路径。"""

    versions = _load_json_object(project_dir / "versions" / "versions.json")
    history = versions[resource_type][resource_id]
    [record] = [item for item in history["versions"] if item["version"] == history["current_version"]]
    (project_dir / record["file"]).unlink()
    return record["file"]


def _register_sample_claim(project_dir: Path, key: ArtifactKey, artifact_path: str) -> None:
    ArtifactManifest(ProjectArtifactManifestAdapter(project_dir)).register(
        key,
        artifact_path=artifact_path,
        basis=ArtifactBasis.build("test/claim", kind_version=1, inputs={"path": artifact_path}),
    )


def claim_reused_item_id_in_the_copying_episode(project_dir: Path, item_id: str) -> None:
    """两集同号 ``item_id``（:func:`reuse_item_id_across_episodes`），共用的分镜图最后由复制来的第 2 集重生。

    清单按路径判重，只容得下一条登记：第 1 集的登记让位，那条登记在第 2 集名下（样本取已激活的
    :func:`write_v19_project`）。
    """

    reuse_item_id_across_episodes(project_dir, item_id)
    ProjectArtifactManifestAdapter(project_dir).delete_entry(ArtifactKey.episode_storyboard(1, item_id))
    _register_sample_claim(project_dir, ArtifactKey.episode_storyboard(2, item_id), f"storyboards/scene_{item_id}.png")


def add_grid_over_reused_item_id(project_dir: Path, item_id: str, grid_id: str = "grid_0123456789ab") -> str:
    """复制来的第 2 集有一张宫格，成员是同号条目 ``item_id`` 与本集另一条 ``E2S02``，切出的分镜图都已登记。

    宫格记录按条目 id 列成员；``E2S02`` 的分镜图是宫格第 2 格。返回宫格 id（样本先经
    :func:`reuse_item_id_across_episodes` 造出同号条目）。
    """

    project = _load_json_object(project_dir / "project.json")
    script_path = project_dir / _ledger_entry(project, 2)["script_file"]
    script = _load_json_object(script_path)
    sibling = {
        **json.loads(json.dumps(script["segments"][0])),
        "segment_id": "E2S02",
        "image_prompt": "宫格第二格",
        "generated_assets": {
            "storyboard_image": "storyboards/scene_E2S02.png",
            "grid_id": grid_id,
            "grid_cell_index": 1,
        },
    }
    script["segments"].append(sibling)
    _write_json(script_path, script)
    (project_dir / "storyboards" / "scene_E2S02.png").write_bytes(b"grid cell 2")
    grid_image = f"grids/{grid_id}.png"
    (project_dir / "grids").mkdir(exist_ok=True)
    (project_dir / grid_image).write_bytes(b"grid composite")
    _write_json(
        project_dir / "grids" / f"{grid_id}.json",
        {
            "id": grid_id,
            "episode": 2,
            "script_file": "scripts/episode_2.json",
            "scene_ids": [item_id, "E2S02"],
            "grid_image_path": grid_image,
            "rows": 1,
            "cols": 2,
            "cell_count": 2,
            "frame_chain": [],
            "status": "completed",
            "prompt": "宫格",
            "provider": "test",
            "model": "test",
            "grid_size": "1K",
            "created_at": "2026-01-01T00:00:00Z",
            "split_at": "2026-01-01T00:00:01Z",
        },
    )
    _register_sample_claim(project_dir, ArtifactKey.episode_grid(2, grid_id), grid_image)
    _register_sample_claim(project_dir, ArtifactKey.episode_storyboard(2, "E2S02"), "storyboards/scene_E2S02.png")
    return grid_id


def write_unreadable_grid_record(project_dir: Path, grid_id: str = "grid_0123456789ab") -> Path:
    """单个宫格记录损坏（不是合法 JSON）。"""

    record = project_dir / "grids" / f"{grid_id}.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_bytes(b"{not json")
    return record


def write_unreadable_script_plan_draft(project_dir: Path, episode: int, name: str) -> Path:
    """单份脚本规划草稿损坏（不是合法 JSON）。"""

    draft = project_dir / "drafts" / f"episode_{episode}" / name
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_bytes(b"{not json")
    return draft


__all__ = [
    "SCHEMA_V19",
    "activate_at_schema_19",
    "add_asset_names_differing_only_in_case",
    "add_asset_names_differing_only_in_whitespace",
    "add_colliding_asset_name",
    "add_grid_over_reused_item_id",
    "break_script_item_ids",
    "claim_reused_item_id_in_the_copying_episode",
    "drop_selected_version_snapshot",
    "refer_to_asset_in_episode",
    "repoint_registered_asset_sheet",
    "reuse_item_id_across_episodes",
    "set_script_episode",
    "share_asset_sheets",
    "share_derivative_sheet",
    "share_reference_files",
    "write_legacy_bare_provider_project",
    "write_legacy_drama_storyboard_project",
    "write_legacy_shared_reference_project",
    "write_legacy_storyboard_project",
    "write_legacy_timeline_project",
    "write_legacy_tts_narration_project",
    "write_unreadable_grid_record",
    "write_unreadable_script_plan_draft",
    "write_v19_project",
]
