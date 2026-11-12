"""音效命令：上传、AI 生成与素材库导入的登记、列出；HTTP、Agent 工具与生成任务共用。

登记流程与 BGM 库共用（:mod:`lib.audio_library.service`）；这里只声明音效的差异：放在 ``sfx/``、实测峰值并统一到
−1 dBFS（增益有上限）、条目记 ``peak_dbfs`` 与 ``added_at``。登记后的音效不能替换或删除。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from lib.audio_library.service import AudioDraft, AudioErrorKind, AudioLibraryKind, AudioLibraryService, AudioMessages
from lib.infra.subprocess_deadline import Spawner
from lib.project.project_manager import ProjectManager
from lib.sfx.library import (
    PROJECT_SFX_FIELD,
    SFX_DIR,
    SFX_EXTENSIONS,
    SFX_MAX_BYTES,
    SFX_NAME_MAX_LENGTH,
    SILENCE_PEAK_DBFS,
    SfxSound,
    peak_gain_db,
    read_sfx_library,
    sfx_basis,
    sfx_entry,
    sfx_file_path,
    sfx_key,
)
from lib.sfx.peak import PeakMeasurementError, measure_peak

type SfxErrorCode = Literal[
    "project_not_found",
    "sfx_unsupported_type",
    "sfx_too_large",
    "sfx_invalid_audio",
    "sfx_silent",
    "sfx_ffmpeg_unavailable",
]


class SfxError(Exception):
    """音效登记无法完成；``code`` 供适配器映射，``params`` 携带定位信息。"""

    def __init__(self, code: SfxErrorCode, message: str, **params: Any) -> None:
        super().__init__(message)
        self.code: SfxErrorCode = code
        self.params = params


_ERROR_CODES: Mapping[AudioErrorKind, SfxErrorCode] = {
    "project_not_found": "project_not_found",
    "unsupported_type": "sfx_unsupported_type",
    "too_large": "sfx_too_large",
    "invalid_audio": "sfx_invalid_audio",
    "silent": "sfx_silent",
    "ffmpeg_unavailable": "sfx_ffmpeg_unavailable",
}


def _error(kind: AudioErrorKind, message: str, /, **params: Any) -> SfxError:
    return SfxError(_ERROR_CODES[kind], message, **params)


def _sound(draft: AudioDraft) -> SfxSound:
    return SfxSound(
        id=draft.id,
        name=draft.name,
        file=draft.file,
        duration_us=draft.duration_us,
        peak_dbfs=round(draft.level, 2),
        gain_db=peak_gain_db(draft.level),
        content_digest=draft.content_digest,
        added_at=draft.registered_at,
        source=draft.source,
        prompt=draft.prompt,
        model=draft.model,
        license=draft.license,
        source_url=draft.source_url,
    )


SFX_LIBRARY = AudioLibraryKind[SfxSound](
    id_prefix="sfx",
    directory=SFX_DIR,
    project_field=PROJECT_SFX_FIELD,
    extensions=SFX_EXTENSIONS,
    max_bytes=SFX_MAX_BYTES,
    name_max_length=SFX_NAME_MAX_LENGTH,
    fallback_name="音效",
    file_path=sfx_file_path,
    measure_level=measure_peak,
    measurement_error=PeakMeasurementError,
    silence_threshold=SILENCE_PEAK_DBFS,
    build=_sound,
    entry=sfx_entry,
    key=sfx_key,
    basis=sfx_basis,
    read=read_sfx_library,
    error=_error,
    messages=AudioMessages(
        unsupported_type="音效只支持 {allowed}，收到 {got}",
        too_large="音效文件过大",
        ffmpeg_unavailable="随包 ffmpeg 不可用，无法测量音效峰值：{detail}",
        unparsable="音效文件无法解析：{detail}",
        no_audio="音效文件里没有可用的音频",
        unmeasurable="音效的峰值测不出来：{detail}",
        silent="音效几乎没有声音，测不出可用的峰值",
        duplicate_id="音效 ID 已被占用：{id}",
    ),
)


class SfxLibraryService(AudioLibraryService[SfxSound]):
    def __init__(self, projects: ProjectManager, *, spawn: Spawner | None = None) -> None:
        super().__init__(SFX_LIBRARY, projects, spawn=spawn)


__all__ = ["SFX_LIBRARY", "SfxError", "SfxErrorCode", "SfxLibraryService"]
