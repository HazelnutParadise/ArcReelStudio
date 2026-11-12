"""BGM 命令：上传、AI 生成与素材库导入的登记、列出；HTTP、Agent 工具与生成任务共用。

登记流程与音效库共用（:mod:`lib.audio_library.service`）；这里只声明 BGM 的差异：放在 ``bgm/``、实测积分响度并
统一到 −16 LUFS、条目记 ``integrated_lufs`` 与 ``uploaded_at``。登记后的 BGM 不能替换或删除。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from lib.audio_library.library import audio_display_name
from lib.audio_library.service import AudioDraft, AudioErrorKind, AudioLibraryKind, AudioLibraryService, AudioMessages
from lib.bgm.library import (
    BGM_DIR,
    BGM_EXTENSIONS,
    BGM_MAX_BYTES,
    BGM_NAME_MAX_LENGTH,
    PROJECT_BGM_FIELD,
    SILENCE_LOUDNESS_LUFS,
    BgmTrack,
    bgm_basis,
    bgm_entry,
    bgm_file_path,
    bgm_key,
    loudness_gain_db,
    read_bgm_library,
)
from lib.bgm.loudness import LoudnessMeasurementError, measure_integrated_loudness
from lib.infra.subprocess_deadline import Spawner
from lib.project.project_manager import ProjectManager

type BgmErrorCode = Literal[
    "project_not_found",
    "bgm_unsupported_type",
    "bgm_too_large",
    "bgm_invalid_audio",
    "bgm_silent",
    "bgm_ffmpeg_unavailable",
]


class BgmError(Exception):
    """BGM 登记无法完成；``code`` 供适配器映射，``params`` 携带定位信息。"""

    def __init__(self, code: BgmErrorCode, message: str, **params: Any) -> None:
        super().__init__(message)
        self.code: BgmErrorCode = code
        self.params = params


_ERROR_CODES: Mapping[AudioErrorKind, BgmErrorCode] = {
    "project_not_found": "project_not_found",
    "unsupported_type": "bgm_unsupported_type",
    "too_large": "bgm_too_large",
    "invalid_audio": "bgm_invalid_audio",
    "silent": "bgm_silent",
    "ffmpeg_unavailable": "bgm_ffmpeg_unavailable",
}


def _error(kind: AudioErrorKind, message: str, /, **params: Any) -> BgmError:
    return BgmError(_ERROR_CODES[kind], message, **params)


def bgm_display_name(filename: str) -> str:
    """BGM 的显示名取文件名去掉扩展名，过长截断；取不出时为「BGM」。"""
    return audio_display_name(filename, max_length=BGM_NAME_MAX_LENGTH, fallback="BGM")


def _track(draft: AudioDraft) -> BgmTrack:
    return BgmTrack(
        id=draft.id,
        name=draft.name,
        file=draft.file,
        duration_us=draft.duration_us,
        integrated_lufs=round(draft.level, 2),
        gain_db=loudness_gain_db(draft.level),
        content_digest=draft.content_digest,
        uploaded_at=draft.registered_at,
        source=draft.source,
        prompt=draft.prompt,
        model=draft.model,
        license=draft.license,
        source_url=draft.source_url,
    )


BGM_LIBRARY = AudioLibraryKind[BgmTrack](
    id_prefix="bgm",
    directory=BGM_DIR,
    project_field=PROJECT_BGM_FIELD,
    extensions=BGM_EXTENSIONS,
    max_bytes=BGM_MAX_BYTES,
    name_max_length=BGM_NAME_MAX_LENGTH,
    fallback_name="BGM",
    file_path=bgm_file_path,
    measure_level=measure_integrated_loudness,
    measurement_error=LoudnessMeasurementError,
    silence_threshold=SILENCE_LOUDNESS_LUFS,
    build=_track,
    entry=bgm_entry,
    key=bgm_key,
    basis=bgm_basis,
    read=read_bgm_library,
    error=_error,
    messages=AudioMessages(
        unsupported_type="BGM 只支持 {allowed}，收到 {got}",
        too_large="BGM 文件过大",
        ffmpeg_unavailable="随包 ffmpeg 不可用，无法测量 BGM 响度：{detail}",
        unparsable="BGM 文件无法解析：{detail}",
        no_audio="BGM 文件里没有可用的音频",
        unmeasurable="BGM 的响度测不出来：{detail}",
        silent="BGM 几乎没有声音，测不出可用的响度",
        duplicate_id="BGM ID 已被占用：{id}",
    ),
)


class BgmLibraryService(AudioLibraryService[BgmTrack]):
    def __init__(self, projects: ProjectManager, *, spawn: Spawner | None = None) -> None:
        super().__init__(BGM_LIBRARY, projects, spawn=spawn)


__all__ = ["BGM_LIBRARY", "BgmError", "BgmErrorCode", "BgmLibraryService", "bgm_display_name"]
