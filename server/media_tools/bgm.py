"""Host-neutral BGM tools: list the project's BGM and generate a new track with the configured music model.

The handler is a thin adapter over the lib BGM command; domain errors keep their stable codes as tool problems.
"""

from __future__ import annotations

import asyncio
import secrets

from pydantic import BaseModel, ConfigDict, Field

from lib.bgm.library import BgmTrack
from lib.bgm.service import BgmError, BgmLibraryService
from server.media_tools.context import tool_error, tool_problem
from server.services.tasks.music_task import MAX_PROMPT_CHARS, MUSIC_TASK_TYPE, music_task_payload
from server.tool_runtime import CallerContext, ProjectScope, Services, ToolOutcome, ToolRequest


class ListBgmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BgmListItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    duration: float


def _item(track: BgmTrack) -> BgmListItem:
    return BgmListItem(id=track.id, name=track.name, duration=track.duration)


async def list_bgm(
    _request: ToolRequest[ListBgmRequest],
    scope: ProjectScope,
    _caller: CallerContext,
    services: Services,
) -> ToolOutcome[tuple[BgmListItem, ...]]:
    try:
        tracks = await BgmLibraryService(services.projects).list(scope.project_name)
    except BgmError as exc:
        return tool_problem(str(exc), code=exc.code, params=exc.params or None)
    except Exception as exc:
        return tool_error("list_bgm", exc)
    return ToolOutcome(value=tuple(_item(track) for track in tracks))


class GenerateMusicRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(
        min_length=1,
        max_length=MAX_PROMPT_CHARS,
        description="音乐的描述：风格、情绪、乐器、节奏，例如「雨夜、慵懒的 lo-fi 钢琴，慢速」",
    )
    duration_seconds: int | None = Field(default=None, ge=3, le=600, description="想要的长度（秒），不给时 60 秒")
    instrumental: bool = Field(default=True, description="只要器乐、不要人声")
    name: str | None = Field(default=None, max_length=80, description="在 BGM 库里显示的名字，不给时取提示词")


class GeneratedMusic(BaseModel):
    model_config = ConfigDict(frozen=True)

    #: 生成完成时的 BGM；远程调用方只拿到排队的任务 id，完成后用 list_bgm 查
    bgm: BgmListItem | None = None
    task_id: str


async def generate_music(
    request: ToolRequest[GenerateMusicRequest],
    scope: ProjectScope,
    caller: CallerContext,
    services: Services,
) -> ToolOutcome[GeneratedMusic]:
    from lib.config.resolver import ConfigResolver
    from lib.db import async_session_factory
    from lib.generation.generation_queue_client import enqueue_and_wait, enqueue_task_only

    args = request.value
    try:
        project = await asyncio.to_thread(services.projects.load_project, scope.project_name)
        resolved = await ConfigResolver(async_session_factory).resolve_music_backend(project, None)
    except ValueError as exc:
        return tool_problem(
            f"还没有设定音乐模型，请创作者在「全局设置 → 默认模型」选择音乐模型（{exc}）",
            code="music_provider_not_configured",
        )
    payload = music_task_payload(
        prompt=args.prompt.strip(),
        provider_id=resolved.provider_id,
        model_id=resolved.model_id,
        credential_id=resolved.credential_id,
        duration_seconds=args.duration_seconds,
        instrumental=args.instrumental,
        name=(args.name or "").strip() or None,
    )
    task = {
        "project_name": scope.project_name,
        "task_type": MUSIC_TASK_TYPE,
        "media_type": "audio",
        "resource_id": f"music-{secrets.token_hex(4)}",
        "payload": payload,
        "source": caller.source,
        "user_id": caller.user_id,
    }
    try:
        if caller.batch_waiter is None:
            queued = await enqueue_task_only(**task)
            return ToolOutcome(value=GeneratedMusic(task_id=queued["task_id"]))
        finished = await enqueue_and_wait(**task)
    except Exception as exc:
        return tool_error("generate_music", exc)
    tracks = {track.id: track for track in await BgmLibraryService(services.projects).list(scope.project_name)}
    track = tracks.get(str(finished["result"].get("bgm_id") or ""))
    return ToolOutcome(
        value=GeneratedMusic(task_id=finished["enqueue"]["task_id"], bgm=_item(track) if track is not None else None)
    )


def generated_music_summary(value: GeneratedMusic) -> str:
    if value.bgm is None:
        return f"音乐生成任务已排队（{value.task_id}）；完成后用 list_bgm 查到这首 BGM"
    return (
        f"已生成 BGM {value.bgm.id}「{value.bgm.name}」{value.bgm.duration} 秒，可用 edit_timeline 的 insert_bgm 摆放"
    )


def bgm_list_summary(items: tuple[BgmListItem, ...]) -> str:
    if not items:
        return "项目里还没有 BGM；可以用 generate_music 生成，或请创作者在剪辑视图的 BGM 轨上传"
    return "\n".join(f"- {item.id}「{item.name}」{item.duration} 秒" for item in items)


__all__ = [
    "BgmListItem",
    "GenerateMusicRequest",
    "GeneratedMusic",
    "ListBgmRequest",
    "bgm_list_summary",
    "generate_music",
    "generated_music_summary",
    "list_bgm",
]
