"""Host-neutral sound effect tools: list the project's sound effects and generate one with the configured model.

The handler is a thin adapter over the lib sound effect command; domain errors keep their stable codes as tool problems.
"""

from __future__ import annotations

import asyncio
import secrets

from pydantic import BaseModel, ConfigDict, Field

from lib.sfx.library import SfxSound
from lib.sfx.service import SfxError, SfxLibraryService
from server.media_tools.context import tool_error, tool_problem
from server.services.tasks.music_task import MAX_PROMPT_CHARS
from server.services.tasks.sfx_task import MAX_SFX_SECONDS, SFX_TASK_TYPE, sfx_task_payload
from server.tool_runtime import CallerContext, ProjectScope, Services, ToolOutcome, ToolRequest


class ListSfxRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SfxListItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    duration: float


def _item(sound: SfxSound) -> SfxListItem:
    return SfxListItem(id=sound.id, name=sound.name, duration=sound.duration)


async def list_sfx(
    _request: ToolRequest[ListSfxRequest],
    scope: ProjectScope,
    _caller: CallerContext,
    services: Services,
) -> ToolOutcome[tuple[SfxListItem, ...]]:
    try:
        sounds = await SfxLibraryService(services.projects).list(scope.project_name)
    except SfxError as exc:
        return tool_problem(str(exc), code=exc.code, params=exc.params or None)
    except Exception as exc:
        return tool_error("list_sfx", exc)
    return ToolOutcome(value=tuple(_item(sound) for sound in sounds))


class GenerateSfxRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(
        min_length=1,
        max_length=MAX_PROMPT_CHARS,
        description="音效的描述：发声物、动作、环境与质感，例如「木门在空房间里被重重关上，带回音」",
    )
    duration_seconds: int | None = Field(
        default=None, ge=1, le=MAX_SFX_SECONDS, description="想要的长度（秒），不给时 3 秒"
    )
    name: str | None = Field(default=None, max_length=80, description="在音效库里显示的名字，不给时取提示词")


class GeneratedSfx(BaseModel):
    model_config = ConfigDict(frozen=True)

    #: 生成完成时的音效；远程调用方只拿到排队的任务 id，完成后用 list_sfx 查
    sfx: SfxListItem | None = None
    task_id: str


async def generate_sfx(
    request: ToolRequest[GenerateSfxRequest],
    scope: ProjectScope,
    caller: CallerContext,
    services: Services,
) -> ToolOutcome[GeneratedSfx]:
    from lib.config.resolver import ConfigResolver
    from lib.db import async_session_factory
    from lib.generation.generation_queue_client import enqueue_and_wait, enqueue_task_only

    args = request.value
    try:
        project = await asyncio.to_thread(services.projects.load_project, scope.project_name)
        resolved = await ConfigResolver(async_session_factory).resolve_sfx_backend(project, None)
    except ValueError as exc:
        return tool_problem(
            f"还没有设定音效模型，请创作者在「全局设置 → 默认模型」选择音效模型（{exc}）",
            code="sfx_provider_not_configured",
        )
    payload = sfx_task_payload(
        prompt=args.prompt.strip(),
        provider_id=resolved.provider_id,
        model_id=resolved.model_id,
        credential_id=resolved.credential_id,
        duration_seconds=args.duration_seconds,
        name=(args.name or "").strip() or None,
    )
    task = {
        "project_name": scope.project_name,
        "task_type": SFX_TASK_TYPE,
        "media_type": "audio",
        "resource_id": f"sfx-{secrets.token_hex(4)}",
        "payload": payload,
        "source": caller.source,
        "user_id": caller.user_id,
    }
    try:
        if caller.batch_waiter is None:
            queued = await enqueue_task_only(**task)
            return ToolOutcome(value=GeneratedSfx(task_id=queued["task_id"]))
        finished = await enqueue_and_wait(**task)
    except Exception as exc:
        return tool_error("generate_sfx", exc)
    sounds = {sound.id: sound for sound in await SfxLibraryService(services.projects).list(scope.project_name)}
    sound = sounds.get(str(finished["result"].get("sfx_id") or ""))
    return ToolOutcome(
        value=GeneratedSfx(task_id=finished["enqueue"]["task_id"], sfx=_item(sound) if sound is not None else None)
    )


def generated_sfx_summary(value: GeneratedSfx) -> str:
    if value.sfx is None:
        return f"音效生成任务已排队（{value.task_id}）；完成后用 list_sfx 查到这个音效"
    return (
        f"已生成音效 {value.sfx.id}「{value.sfx.name}」{value.sfx.duration} 秒，可用 edit_timeline 的 insert_sfx 摆放"
    )


def sfx_list_summary(items: tuple[SfxListItem, ...]) -> str:
    if not items:
        return "项目里还没有音效；可以用 generate_sfx 生成，或请创作者在剪辑视图的音效轨上传"
    return "\n".join(f"- {item.id}「{item.name}」{item.duration} 秒" for item in items)


__all__ = [
    "GenerateSfxRequest",
    "GeneratedSfx",
    "ListSfxRequest",
    "SfxListItem",
    "generate_sfx",
    "generated_sfx_summary",
    "list_sfx",
    "sfx_list_summary",
]
