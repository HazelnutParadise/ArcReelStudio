"""音乐生成任务：一段提示词经选定的音乐模型生成一首 BGM，登记进项目的 BGM 库（docs/adr/0126）。

入队时就解析好用哪个 ``provider/model`` 与连线并冻结在 payload（``music_provider`` / ``music_model`` /
``music_provider_credential_id``），佇列投影与执行都照它，不会因中途改了设定而换模型。生成结果走与上传相同的 BGM 登记：
统一响度到 −16 LUFS、按字节登记产物，并记下提示词与模型。
"""

from __future__ import annotations

import asyncio
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Any

from lib.backends.backend_assembly.assembler import assemble_backend, assembled_credential_id
from lib.backends.music_backends import MusicGenerationRequest
from lib.bgm.service import BgmLibraryService
from lib.billing.ledger import Ledger
from lib.billing.metering import Usage
from lib.config.resolver import ConfigResolver
from lib.db.base import DEFAULT_USER_ID

MUSIC_TASK_TYPE = "music"
#: 一次生成没给长度时的预设秒数
DEFAULT_MUSIC_SECONDS = 60
MAX_PROMPT_CHARS = 2000


def music_task_payload(
    *,
    prompt: str,
    provider_id: str,
    model_id: str,
    credential_id: int | None,
    duration_seconds: int | None = None,
    instrumental: bool = True,
    name: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": prompt,
        "music_provider": provider_id,
        "music_model": model_id,
        "instrumental": instrumental,
    }
    if credential_id is not None:
        payload["music_provider_credential_id"] = credential_id
    if duration_seconds:
        payload["duration_seconds"] = duration_seconds
    if name:
        payload["name"] = name
    return payload


def _usage(provider_meter_seconds: float | None) -> Usage:
    """按次计价的模型取 ``requests``，按秒计价的取 ``output_seconds``；计算器只取价目表里有的那一项。"""
    quantities: dict[str, float] = {"requests": 1}
    if provider_meter_seconds:
        quantities["output_seconds"] = float(provider_meter_seconds)
    return Usage(quantities=quantities)


async def execute_music_task(
    project_name: str,
    resource_id: str,
    payload: dict[str, Any],
    *,
    user_id: str = DEFAULT_USER_ID,
    task_id: str | None = None,
    claimed_provider_id: str | None = None,
) -> dict[str, Any]:
    del claimed_provider_id
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("music task 需要 payload.prompt")
    # 晚导入：与其他任务执行入口一样经 lib.db / lib.config.resolver 取共用的会话工厂与项目管理器
    from lib.config import resolver as resolver_module
    from lib.db import async_session_factory

    projects = resolver_module.get_project_manager()
    resolver = ConfigResolver(async_session_factory)
    project = await asyncio.to_thread(projects.load_project, project_name)
    resolved = await resolver.resolve_music_backend(project, payload)
    backend = await assemble_backend(
        provider_id=resolved.provider_id,
        media_type="audio",
        model_id=resolved.model_id,
        resolver=resolver,
        credential_id=resolved.credential_id,
    )
    if not hasattr(backend, "generate"):
        raise ValueError(f"{resolved.provider_id}/{resolved.model_id} 不是音乐模型")
    duration = payload.get("duration_seconds")
    seconds = duration if isinstance(duration, int) and duration > 0 else DEFAULT_MUSIC_SECONDS
    instrumental = payload.get("instrumental") is not False
    tmp = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="arcreel-music-"))
    try:
        output_path = tmp / f"music-{secrets.token_hex(4)}.mp3"
        async with Ledger(session_factory=async_session_factory).record(
            project_name=project_name,
            call_type="audio",
            model=resolved.model_id,
            provider=resolved.provider_id,
            prompt=prompt,
            duration_seconds=seconds,
            user_id=user_id,
            task_id=task_id,
            credential_id=assembled_credential_id(backend),
        ) as call:
            result = await backend.generate(
                MusicGenerationRequest(
                    prompt=prompt, output_path=output_path, duration_seconds=seconds, instrumental=instrumental
                )
            )
            call.success(result, usage=_usage(result.duration_seconds))
        content = await asyncio.to_thread(output_path.read_bytes)
    finally:
        await asyncio.to_thread(shutil.rmtree, tmp, ignore_errors=True)  # hard-delete: temp -- 生成暂存目录
    track = await BgmLibraryService(projects).register_generated(
        project_name,
        name=str(payload.get("name") or prompt)[:80],
        extension=output_path.suffix,
        content=content,
        prompt=prompt,
        model=f"{resolved.provider_id}/{resolved.model_id}",
    )
    return {"bgm_id": track.id, "name": track.name, "file": track.file, "resource_id": resource_id}


__all__ = [
    "DEFAULT_MUSIC_SECONDS",
    "MAX_PROMPT_CHARS",
    "MUSIC_TASK_TYPE",
    "execute_music_task",
    "music_task_payload",
]
