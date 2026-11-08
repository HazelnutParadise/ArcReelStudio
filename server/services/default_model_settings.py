"""全局「默认模型」页的设置：系统设置接口与该页的协作写回走同一套校验与写入。

包括引用模型的字段与各自的连线旁键、旁白音色与语速、视频是否生成音轨、视频轮询超时。不合规时抛
:class:`~lib.infra.api_errors.ApiError`，由调用方翻成 HTTP 响应或协作错误；写入不提交，提交由调用方负责。
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from lib.config.model_setting_keys import GLOBAL_MODEL_SETTING_KEYS, credential_key, parse_credential_id
from lib.config.service import DEFAULT_VIDEO_POLL_TIMEOUT_SECONDS, ConfigService
from lib.infra.api_errors import UnprocessableError
from server.services.backend_values import validate_backend_credential, validate_backend_value

#: 默认模型页能改的设置项
DEFAULT_MODEL_SETTING_FIELDS: tuple[str, ...] = (
    *GLOBAL_MODEL_SETTING_KEYS,
    *(credential_key(key) for key in GLOBAL_MODEL_SETTING_KEYS),
    "narration_voice",
    "narration_speed",
    "video_generate_audio",
    "video_poll_timeout_seconds",
)


async def read_default_model_settings(svc: ConfigService) -> dict[str, Any]:
    """默认模型页的设置，取值形态与 ``GET /system/config`` 的同名字段一致。"""
    settings = await svc.get_all_settings()
    raw_audio = settings.get("video_generate_audio", "")
    return {
        **{key: settings.get(key, "") for key in GLOBAL_MODEL_SETTING_KEYS},
        **{
            credential_key(key): parse_credential_id(settings.get(credential_key(key)))
            for key in GLOBAL_MODEL_SETTING_KEYS
        },
        "narration_voice": settings.get("narration_voice", ""),
        "narration_speed": ConfigService.parse_narration_speed(settings.get("narration_speed", "")),
        "video_generate_audio": raw_audio.lower() in ("true", "1", "yes") if raw_audio else True,
        "video_poll_timeout_seconds": ConfigService.parse_video_poll_timeout_seconds(
            settings.get("video_poll_timeout_seconds") or str(DEFAULT_VIDEO_POLL_TIMEOUT_SECONDS)
        ),
    }


async def apply_default_model_settings(session: AsyncSession, svc: ConfigService, patch: dict[str, Any]) -> None:
    """写入 ``patch`` 里出现的默认模型页设置项；其余键忽略。"""
    current_settings = await svc.get_all_settings()
    for backend_key in GLOBAL_MODEL_SETTING_KEYS:
        current = current_settings.get(backend_key, "")
        effective = current
        if backend_key in patch:
            effective = str(patch[backend_key] or "").strip()
            if effective:
                validate_backend_value(effective, backend_key)
            await svc.set_setting(backend_key, effective)
        # 连线跟着同一字段的供应商走：指定时核对属于该供应商；换了供应商又没重选连线时回到默认连线
        cred_key = credential_key(backend_key)
        if cred_key in patch:
            stored = await validate_backend_credential(session, effective, parse_credential_id(patch[cred_key]))
            await svc.set_setting(cred_key, str(stored) if stored else "")
        elif backend_key in patch and _provider_of(effective) != _provider_of(current):
            await svc.set_setting(cred_key, "")

    # 旁白音色：可配置字符串 id（照供应商文档填），空串 = 清除回落服务默认
    if "narration_voice" in patch:
        await svc.set_setting("narration_voice", str(patch["narration_voice"] or "").strip())

    # 旁白语速：仅做正有限数卫生校验（拒绝 0/负数/inf/nan），具体取值范围由各供应商自行约束；null = 清除
    if "narration_speed" in patch:
        speed = patch["narration_speed"]
        if speed is None:
            await svc.set_setting("narration_speed", "")
        else:
            speed = float(speed)
            if not math.isfinite(speed) or speed <= 0:
                raise UnprocessableError("narration_speed_must_be_positive")
            await svc.set_setting("narration_speed", str(speed))

    if "video_generate_audio" in patch and patch["video_generate_audio"] is not None:
        await svc.set_setting("video_generate_audio", "true" if patch["video_generate_audio"] else "false")

    if "video_poll_timeout_seconds" in patch and patch["video_poll_timeout_seconds"] is not None:
        try:
            await svc.set_video_poll_timeout_seconds(int(patch["video_poll_timeout_seconds"]))
        except (TypeError, ValueError) as exc:
            raise UnprocessableError("video_poll_timeout_minimum") from exc


def _provider_of(backend_value: str) -> str:
    return backend_value.split("/", 1)[0] if backend_value else ""
