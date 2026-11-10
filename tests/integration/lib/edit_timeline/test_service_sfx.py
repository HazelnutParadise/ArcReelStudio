"""剪辑时间线的音效片段：在真实临时项目上经公开服务命令验证增删改、可重叠的摆放、读取形态与缺失阻断。"""

from __future__ import annotations

from typing import Any

import pytest

from lib.edit_timeline import EditTimelineError, EditTimelineService, RevisionAuthor
from lib.edit_timeline.operations import TimelineOperationAdapter
from lib.project.project_manager import ProjectManager
from lib.sfx.service import SfxLibraryService
from tests.factories import wav_bytes

AGENT = RevisionAuthor(kind="arcreel_agent")


@pytest.fixture
async def sfx_id(pm: ProjectManager) -> str:
    """一个 1 秒的音效。"""
    sound = await SfxLibraryService(pm).upload("demo", filename="关门.wav", content=wav_bytes(1.0, tone_hz=440))
    return sound.id


async def _create(service: EditTimelineService) -> str:
    created = await service.create_from_script("demo", episode=1, name="初剪", author=AGENT)
    return created.timeline.id


async def _edit(service: EditTimelineService, timeline_id: str, base_revision: int, *operations: dict[str, Any]):
    return await service.edit(
        "demo",
        timeline_id,
        base_revision=base_revision,
        summary="加音效",
        operations=[TimelineOperationAdapter.validate_python(operation) for operation in operations],
        author=AGENT,
    )


def _rows(sfx: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    return [
        (
            clip.id,
            clip.name,
            clip.start,
            clip.end,
            clip.source_in,
            clip.source_out,
            clip.volume,
            clip.fade_in,
            clip.fade_out,
        )
        for clip in sfx
    ]


@pytest.mark.usefixtures("three_clips")
async def test_sound_effects_may_overlap_and_are_cut_at_the_timeline_end(
    service: EditTimelineService, sfx_id: str
) -> None:
    timeline_id = await _create(service)

    result = await _edit(
        service,
        timeline_id,
        1,
        {"op": "insert_sfx", "sfx_id": sfx_id, "start": 0.5},
        {"op": "insert_sfx", "sfx_id": sfx_id, "start": 0.8, "volume": 0.5, "fade_in": 0.1},
        {"op": "insert_sfx", "sfx_id": sfx_id, "start": 2.5},
    )

    assert result.revision == 2
    readout = await service.read("demo", timeline_id)
    assert readout.duration == 3.0
    # s1 与 s2 重叠也照常放；s3 越过 3 秒的末尾，截到末尾，截断处淡出 0.05 秒
    assert _rows(readout.sfx) == [
        ("s1", "关门", 0.5, 1.5, 0.0, 1.0, 1.0, 0.0, 0.0),
        ("s2", "关门", 0.8, 1.8, 0.0, 1.0, 0.5, 0.1, 0.0),
        ("s3", "关门", 2.5, 3.0, 0.0, 1.0, 1.0, 0.0, 0.05),
    ]
    assert [issue for issue in readout.issues if issue.code.value == "sfx_missing"] == []


@pytest.mark.usefixtures("three_clips")
async def test_set_and_delete_sfx_change_only_the_named_clip(service: EditTimelineService, sfx_id: str) -> None:
    timeline_id = await _create(service)
    await _edit(
        service,
        timeline_id,
        1,
        {"op": "insert_sfx", "sfx_id": sfx_id, "start": 0},
        {"op": "insert_sfx", "sfx_id": sfx_id, "start": 1},
    )

    await _edit(
        service,
        timeline_id,
        2,
        {"op": "set_sfx", "clip": "s1", "start": 0.2, "source_in": 0.25, "volume": 0.6, "fade_out": 0.2},
        {"op": "delete_sfx", "clip": "s2"},
    )

    readout = await service.read("demo", timeline_id)
    assert _rows(readout.sfx) == [("s1", "关门", 0.2, 0.95, 0.25, 1.0, 0.6, 0.0, 0.2)]


@pytest.mark.usefixtures("three_clips")
@pytest.mark.parametrize(
    ("operation", "field"),
    [
        ({"op": "insert_sfx", "sfx_id": "sfx-0000ffff", "start": 0}, "sfx_id"),
        ({"op": "insert_sfx", "start": 5}, "start"),
        ({"op": "insert_sfx", "start": 0, "source_in": 0.5, "source_out": 0.55}, "source_in/source_out"),
        ({"op": "insert_sfx", "start": 0, "volume": 1.5}, "volume"),
    ],
)
async def test_invalid_sound_effect_operations_are_refused(
    service: EditTimelineService, sfx_id: str, operation: dict[str, Any], field: str
) -> None:
    timeline_id = await _create(service)

    with pytest.raises(EditTimelineError) as refused:
        await _edit(service, timeline_id, 1, {"sfx_id": sfx_id, **operation})

    assert refused.value.code == "operation_invalid"
    assert refused.value.params["field"] == field


@pytest.mark.usefixtures("three_clips")
async def test_a_sound_effect_whose_file_is_gone_blocks_rendering(
    service: EditTimelineService, pm: ProjectManager, sfx_id: str
) -> None:
    timeline_id = await _create(service)
    await _edit(service, timeline_id, 1, {"op": "insert_sfx", "sfx_id": sfx_id, "start": 0})
    (pm.get_project_path("demo") / "sfx" / f"{sfx_id}.wav").unlink()

    readout = await service.read("demo", timeline_id)

    [issue] = [issue for issue in readout.issues if issue.code.value == "sfx_missing"]
    assert issue.clip_ids == ("s1",)
