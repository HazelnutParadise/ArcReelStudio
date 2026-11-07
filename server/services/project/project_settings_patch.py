"""项目设置的修改：项目 PATCH 接口与项目设置的协作写回走同一套校验与写入。

:class:`ProjectSettingsPatch` 里出现的字段（``model_fields_set``）才会写入；显式 null 按各字段的语义清除或拒绝。
不合规时抛 :class:`~lib.infra.api_errors.ApiError`（带 i18n key 与参数），由调用方翻成 HTTP 响应或协作错误。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

from lib.episode.episode_target_duration import (
    EPISODE_TARGET_DURATION_FIELD,
    MAX_EPISODE_TARGET_DURATION,
    MIN_EPISODE_TARGET_DURATION,
    is_valid_episode_target_duration,
)
from lib.infra.api_errors import BadRequestError, UnprocessableError
from lib.prompts.style_templates import is_known_template, resolve_template_prompt
from lib.speech.character_voice import PROJECT_FIELD as CHARACTER_VOICE_BINDING_FIELD
from lib.speech.character_voice import VALID_CHARACTER_VOICE_BINDINGS
from lib.speech.narration_config import (
    NARRATION_DELIVERY_FIELD,
    TTS_BACKEND_FIELD,
    TTS_SPEED_FIELD,
    TTS_VOICE_FIELD,
    NarrationConfigError,
    NarrationDelivery,
    validate_project_narration_config,
)
from lib.speech.speech_rate import MAX_SPEECH_RATE_UPS, MIN_SPEECH_RATE_UPS, SPEECH_RATE_FIELD, is_valid_speech_rate
from server.services.backend_values import validate_backend_value
from server.services.project.narration_settings import validate_tts_backend, validate_tts_speed

#: 项目级模型覆盖字段：空值即清除、继承全局。
PROJECT_BACKEND_FIELDS = (
    "video_backend",
    "video_provider_i2v",
    "video_provider_r2v",
    "image_provider_t2i",
    "image_provider_i2i",
    "default_image_backend",
    "text_backend_simple",
    "text_backend_complex",
    "default_text_backend",
)


def _reject_bool_speech_rate(value: object) -> object:
    """布尔不是语速：Pydantic 非严格模式会把 JSON ``true`` 折成 1.0、``false`` 折成 0.0。

    真相源与数据校验器都把 bool 判为脏值，写入侧若放行，落库后的 1.0 已无从辨认原本是布尔，
    而 0.0 又会被当成「未填」跳过写入——同一类输入两种结局。在进入区间校验前直接拒。
    """
    if isinstance(value, bool):
        raise ValueError("speech rate must be a number, not a boolean")
    return value


#: 创建 / 修改项目时的口播语速估算字段类型，共用同一把布尔守卫。
SpeechRateOverride = Annotated[float | None, BeforeValidator(_reject_bool_speech_rate)]


def validated_episode_target_duration(value: int) -> int:
    """把单集目标时长收进硬区间，越界即 422。

    区间与 ``lib.episode.episode_target_duration`` 的读时守卫、``patch_project`` 的强制转换、
    前端输入校验同一把尺（``is_valid_episode_target_duration``），不在这里另写边界数字。
    """
    if not is_valid_episode_target_duration(value):
        raise UnprocessableError(
            "episode_target_duration_out_of_range",
            min=MIN_EPISODE_TARGET_DURATION,
            max=MAX_EPISODE_TARGET_DURATION,
        )
    return value


def validated_speech_rate(value: float) -> float:
    """把口播语速估算收进硬区间，越界即 422（区间同 ``is_valid_speech_rate``）。"""
    rate = float(value)
    if not is_valid_speech_rate(rate):
        raise UnprocessableError("speech_rate_out_of_range", min=MIN_SPEECH_RATE_UPS, max=MAX_SPEECH_RATE_UPS)
    return rate


class ProjectSettingsPatch(BaseModel):
    """项目设置页能改的字段。"""

    aspect_ratio: str | None = None
    default_duration: int | None = None
    # 单集目标时长（秒）：显式 null 清除该偏好；ad 项目对字段出现本身即拒绝
    episode_target_duration: int | None = None
    # 仅 ad 项目：目标总时长（秒），任意正整数合法，不可清空
    target_duration: int | None = Field(default=None, gt=0)
    # 生成模式创建即定、不可变，这里结构上没有 generation_mode；宫格开关随时可切
    grid_storyboard: bool | None = None
    video_backend: str | None = None
    video_provider_i2v: str | None = None
    video_provider_r2v: str | None = None
    image_provider_t2i: str | None = None
    image_provider_i2i: str | None = None
    default_image_backend: str | None = None
    video_generate_audio: bool | None = None
    # 角色声音绑定方式：prompt（默认，voice_style 提示词软约束）/ reference_audio（挂角色参考音频）
    character_voice_binding: str | None = None
    # 旁白交付方式（docs/adr/0089）：随时可改，不让任何已有产物过期；不可清空
    narration_delivery: NarrationDelivery | None = None
    # 旁白配音（TTS）快照：模型（provider/model）/ 音色 / 配音语速，不继承全局默认。
    # TTS 配音项目的模型与音色不可清空；语速 null = 不向供应商传语速
    audio_backend: str | None = None
    narration_voice: str | None = None
    narration_speed: float | None = None
    # 口播语速估算（阅读单位 / 秒）项目级覆盖；null = 清除、回退语言默认
    speech_rate_units_per_second: SpeechRateOverride = None
    # 文本任务档位（docs/adr/0051）项目级覆盖 + 项目默认模型；空值 = 清除、继承全局
    text_backend_simple: str | None = None
    text_backend_complex: str | None = None
    default_text_backend: str | None = None
    style_template_id: str | None = None
    clear_style_image: bool | None = None
    model_settings: dict[str, dict[str, str | None]] | None = None


def apply_project_settings_patch(project: dict, patch: ProjectSettingsPatch) -> None:
    """把 ``patch`` 里出现的字段写进 ``project``（原地修改）；不合规时抛 ``ApiError``，调用方整次放弃。"""
    fields = patch.model_fields_set
    is_ad = project.get("content_mode") == "ad"
    for field in PROJECT_BACKEND_FIELDS:
        if field in fields:
            value = getattr(patch, field)
            if value:
                validate_backend_value(value, field)
                project[field] = value
            else:
                project.pop(field, None)

    if "video_generate_audio" in fields:
        if patch.video_generate_audio is None:
            project.pop("video_generate_audio", None)
        else:
            project["video_generate_audio"] = patch.video_generate_audio
    # 角色声音绑定方式：枚举，null / 空串 = 清除、回落默认（提示词软约束）
    if "character_voice_binding" in fields:
        binding = (patch.character_voice_binding or "").strip()
        if not binding:
            project.pop(CHARACTER_VOICE_BINDING_FIELD, None)
        elif binding in VALID_CHARACTER_VOICE_BINDINGS:
            project[CHARACTER_VOICE_BINDING_FIELD] = binding
        else:
            raise UnprocessableError("character_voice_binding_invalid")
    _apply_narration(project, patch)
    # 口播语速估算（阅读单位 / 秒）：宽松硬区间，null = 清除、回退语言默认
    if "speech_rate_units_per_second" in fields:
        if patch.speech_rate_units_per_second is None:
            project.pop(SPEECH_RATE_FIELD, None)
        else:
            project[SPEECH_RATE_FIELD] = validated_speech_rate(patch.speech_rate_units_per_second)
    if "aspect_ratio" in fields and patch.aspect_ratio is not None:
        project["aspect_ratio"] = patch.aspect_ratio
    if "grid_storyboard" in fields:
        if is_ad and patch.grid_storyboard:
            raise BadRequestError("ad_grid_not_supported")
        # null 与 false 同义：宫格关闭态落盘为显式 false，与创建路径同形态
        project["grid_storyboard"] = bool(patch.grid_storyboard)
    if "default_duration" in fields:
        # ad 项目对字段出现本身即拒绝（含 null）：与创建路径「禁写字段」契约一致，避免 null 走删除分支静默成功
        if is_ad:
            raise BadRequestError("ad_no_default_duration")
        if patch.default_duration is None:
            project.pop("default_duration", None)
        else:
            project["default_duration"] = patch.default_duration
    if "episode_target_duration" in fields:
        # 与 default_duration 同口径：ad 项目对字段出现本身即拒绝（含 null）
        if is_ad:
            raise BadRequestError("ad_no_episode_target_duration")
        if patch.episode_target_duration is None:
            project.pop(EPISODE_TARGET_DURATION_FIELD, None)
        else:
            project[EPISODE_TARGET_DURATION_FIELD] = validated_episode_target_duration(patch.episode_target_duration)
    if "target_duration" in fields:
        if not is_ad:
            raise BadRequestError("ad_only_field", field="target_duration")
        if patch.target_duration is None:
            raise BadRequestError("ad_target_duration_required")
        project["target_duration"] = patch.target_duration

    if "style_template_id" in fields:
        if not patch.style_template_id:
            # 取消模版选择：同时清掉展开的 style prompt，避免遗留孤儿文本
            project.pop("style_template_id", None)
            project["style"] = ""
        else:
            if not is_known_template(patch.style_template_id):
                raise BadRequestError("unknown_style_template", template_id=patch.style_template_id)
            project["style_template_id"] = patch.style_template_id
            project["style"] = resolve_template_prompt(patch.style_template_id)
            # 强互斥：模版与参考图二选一
            project.pop("style_image", None)
            project.pop("style_description", None)

    if patch.clear_style_image:
        # 显式清除自定义参考图，用于「取消风格」流程
        project.pop("style_image", None)
        project.pop("style_description", None)

    if "model_settings" in fields:
        if patch.model_settings is None:
            project.pop("model_settings", None)
        else:
            project["model_settings"] = patch.model_settings


def _apply_narration(project: dict, patch: ProjectSettingsPatch) -> None:
    """写入旁白交付方式与 TTS 快照；改完后 TTS 配音项目仍须带完整快照，否则整次 422。

    交付方式不进产物的生成依据：切换交付方式不让已有产物过期，改为后期配音时 TTS 快照保留。
    """
    fields = patch.model_fields_set
    try:
        if "narration_delivery" in fields:
            if patch.narration_delivery is None:
                raise NarrationConfigError("narration_delivery_required")
            project[NARRATION_DELIVERY_FIELD] = patch.narration_delivery
        if TTS_BACKEND_FIELD in fields:
            if patch.audio_backend:
                validate_backend_value(patch.audio_backend, TTS_BACKEND_FIELD)
                project[TTS_BACKEND_FIELD] = validate_tts_backend(patch.audio_backend)
            else:
                project.pop(TTS_BACKEND_FIELD, None)
        # 音色是照供应商文档填的字符串 id；空串 = 清除
        if TTS_VOICE_FIELD in fields:
            voice = (patch.narration_voice or "").strip()
            if voice:
                project[TTS_VOICE_FIELD] = voice
            else:
                project.pop(TTS_VOICE_FIELD, None)
        # 配音语速只做正有限数卫生校验，取值范围由各供应商约束
        if TTS_SPEED_FIELD in fields:
            if patch.narration_speed is None:
                project.pop(TTS_SPEED_FIELD, None)
            else:
                project[TTS_SPEED_FIELD] = validate_tts_speed(patch.narration_speed)
        validate_project_narration_config(project)
    except NarrationConfigError as exc:
        raise UnprocessableError(exc.code) from exc
