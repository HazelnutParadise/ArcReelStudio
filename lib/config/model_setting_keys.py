"""引用模型的设置字段名：全局 ``system_settings`` 与项目 ``project.json`` 各自哪些键的值是 ``provider/model``。

每个引用模型的字段旁边可以有一个同层的「连线」旁键 ``<字段>_credential_id``：指定用该供应商的哪一条凭证；
没有时用该供应商的默认连线（``provider_credential.is_active``）。连线随取到模型的那一层走，不跨层混用。
"""

from __future__ import annotations

#: 全局 system_settings 与项目 project.json 同名的文本 backend 字段。
TEXT_BACKEND_SETTING_KEYS: tuple[str, ...] = (
    "default_text_backend",
    "text_backend_simple",
    "text_backend_complex",
)

#: 全局 system_settings 里所有引用模型的设置项。
GLOBAL_MODEL_SETTING_KEYS: tuple[str, ...] = (
    *TEXT_BACKEND_SETTING_KEYS,
    "default_image_backend",
    "default_image_backend_t2i",
    "default_image_backend_i2i",
    "default_video_backend",
    "default_video_backend_i2v",
    "default_video_backend_r2v",
    "default_audio_backend",
)

#: 项目 project.json 里所有引用模型的字段。
PROJECT_MODEL_SETTING_KEYS: tuple[str, ...] = (
    *TEXT_BACKEND_SETTING_KEYS,
    "default_image_backend",
    "image_provider_t2i",
    "image_provider_i2i",
    "video_backend",
    "video_provider_i2v",
    "video_provider_r2v",
    "audio_backend",
)

#: 引用模型的设置字段（全局与项目）→ 所引模型的媒体类型。写入时据此校验模型的媒体类型，读出引用时据此对应条目。
MODEL_SETTING_MEDIA_TYPES: dict[str, str] = {
    "video_backend": "video",
    "video_provider_i2v": "video",
    "video_provider_r2v": "video",
    "default_video_backend": "video",
    "default_video_backend_i2v": "video",
    "default_video_backend_r2v": "video",
    "image_provider_t2i": "image",
    "image_provider_i2i": "image",
    "default_image_backend": "image",
    "default_image_backend_t2i": "image",
    "default_image_backend_i2i": "image",
    "audio_backend": "audio",
    "default_audio_backend": "audio",
    "text_backend_simple": "text",
    "text_backend_complex": "text",
    "default_text_backend": "text",
}


#: 「连线」旁键的后缀：``<引用模型的字段><后缀>`` 存所指定的凭证 id。
CREDENTIAL_KEY_SUFFIX = "_credential_id"


def credential_key(model_key: str) -> str:
    """引用模型的字段对应的连线旁键名。"""
    return f"{model_key}{CREDENTIAL_KEY_SUFFIX}"


def parse_credential_id(raw: object) -> int | None:
    """连线旁键的值 → 凭证 id；空值、非正整数一律为 None（用默认连线）。

    全局设置是字符串键值，项目文件是 JSON，两种写法都接受。
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw > 0 else None
    if isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
        return value if value > 0 else None
    return None
