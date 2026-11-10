"""音效生成任务：一段提示词经选定的音效模型生成一个音效，登记进项目的音效库（docs/adr/0127）。

入队时就解析好用哪个 ``provider/model`` 与连线并冻结在 payload（``sfx_provider`` / ``sfx_model`` /
``sfx_provider_credential_id``），佇列投影与执行都照它。生成结果走与上传相同的音效登记：统一峰值到 −1 dBFS、
按字节登记产物，并记下提示词与模型。
"""

from __future__ import annotations

import asyncio
from typing import Any

from lib.config.resolver import ConfigResolver
from lib.db.base import DEFAULT_USER_ID
from lib.sfx.service import SfxLibraryService
from server.services.tasks.music_task import generate_prompted_audio, task_prompt

SFX_TASK_TYPE = "sfx"
#: 一次生成没给长度时的预设秒数
DEFAULT_SFX_SECONDS = 3
MAX_SFX_SECONDS = 30


def sfx_task_payload(
    *,
    prompt: str,
    provider_id: str,
    model_id: str,
    credential_id: int | None,
    duration_seconds: int | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"prompt": prompt, "sfx_provider": provider_id, "sfx_model": model_id}
    if credential_id is not None:
        payload["sfx_provider_credential_id"] = credential_id
    if duration_seconds:
        payload["duration_seconds"] = duration_seconds
    if name:
        payload["name"] = name
    return payload


async def execute_sfx_task(
    project_name: str,
    resource_id: str,
    payload: dict[str, Any],
    *,
    user_id: str = DEFAULT_USER_ID,
    task_id: str | None = None,
    claimed_provider_id: str | None = None,
) -> dict[str, Any]:
    del claimed_provider_id
    prompt = task_prompt(payload, SFX_TASK_TYPE)
    # 晚导入：与其他任务执行入口一样经 lib.db / lib.config.resolver 取共用的会话工厂与项目管理器
    from lib.config import resolver as resolver_module
    from lib.db import async_session_factory

    projects = resolver_module.get_project_manager()
    resolver = ConfigResolver(async_session_factory)
    project = await asyncio.to_thread(projects.load_project, project_name)
    resolved = await resolver.resolve_sfx_backend(project, payload)
    duration = payload.get("duration_seconds")
    seconds = duration if isinstance(duration, int) and duration > 0 else DEFAULT_SFX_SECONDS
    content, extension = await generate_prompted_audio(
        project_name,
        resolved,
        resolver=resolver,
        prompt=prompt,
        seconds=min(seconds, MAX_SFX_SECONDS),
        instrumental=True,
        user_id=user_id,
        task_id=task_id,
        temp_prefix="arcreel-sfx-",
        session_factory=async_session_factory,
    )
    sound = await SfxLibraryService(projects).register_generated(
        project_name,
        name=str(payload.get("name") or prompt)[:80],
        extension=extension,
        content=content,
        prompt=prompt,
        model=f"{resolved.provider_id}/{resolved.model_id}",
    )
    return {"sfx_id": sound.id, "name": sound.name, "file": sound.file, "resource_id": resource_id}


__all__ = ["DEFAULT_SFX_SECONDS", "MAX_SFX_SECONDS", "SFX_TASK_TYPE", "execute_sfx_task", "sfx_task_payload"]
