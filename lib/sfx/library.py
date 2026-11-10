"""项目级音效库的存储形态、产物身份与生成依据（``docs/adr/0127``）。

每个音效的元数据记在 ``project.json`` 的 ``sfx`` 下，键是音效 ID，值是名称、文件、时长、实测峰值与折算增益；
文件放在 ``sfx/<音效 ID><扩展名>``，登记后不再改写。产物身份是音效 ID，生成依据只有文件字节的内容指纹。

音效多半只有零点几秒到几十秒，积分响度对这么短的瞬态不稳定，所以不像 BGM 那样统一积分响度，而是按实测峰值
折算成把峰值统一到 :data:`TARGET_PEAK_DBFS` 的静态增益；成片与剪映草稿里音效片段的实际音量是这个增益乘以片段音量。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from lib.artifacts.artifact_manifest import ArtifactBasis, ArtifactKey

SFX_DIR = "sfx"
PROJECT_SFX_FIELD = "sfx"
"""``project.json`` 里音效库所在的字段。"""

SFX_ID_PATTERN = r"^sfx-[0-9a-f]{8}$"
SFX_EXTENSIONS = (".mp3", ".wav", ".m4a")
SFX_MAX_BYTES = 30 * 1024 * 1024
SFX_NAME_MAX_LENGTH = 80

TARGET_PEAK_DBFS = -1.0
"""音效峰值统一到的电平。"""

SILENCE_PEAK_DBFS = -60.0
"""峰值不高于它说明整段几乎无声，折算不出可用的增益。"""

MAX_GAIN_DB = 24.0
"""折算增益的上限：很小声的音效不会被拉高到底噪都清晰可闻。"""

SFX_BASIS_KIND = "project-sfx"
SFX_BASIS_VERSION = 1

_SFX_ID_RE = re.compile(SFX_ID_PATTERN)

#: 音效从哪来：使用者上传、AI 生成
SfxOrigin = Literal["upload", "ai"]


class SfxSound(BaseModel):
    """一个已登记的音效。``gain_db`` 是把实测峰值统一到 −1 dBFS 的静态增益。"""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str = Field(pattern=SFX_ID_PATTERN)
    name: str = Field(min_length=1, max_length=SFX_NAME_MAX_LENGTH)
    file: str = Field(min_length=1)
    duration_us: int = Field(gt=0, strict=True)
    peak_dbfs: float
    gain_db: float
    content_digest: str = Field(min_length=1)
    added_at: str
    source: SfxOrigin = "upload"
    prompt: str | None = None
    model: str | None = None

    @property
    def gain(self) -> float:
        return 10 ** (self.gain_db / 20)

    @property
    def duration(self) -> float:
        return round(self.duration_us / 1_000_000, 3)


def is_sfx_id(value: object) -> bool:
    return isinstance(value, str) and _SFX_ID_RE.fullmatch(value) is not None


def sfx_file_path(sfx_id: str, extension: str) -> str:
    return f"{SFX_DIR}/{sfx_id}{extension}"


def peak_gain_db(peak_dbfs: float) -> float:
    """把实测峰值统一到 :data:`TARGET_PEAK_DBFS` 的增益（dB），不超过 :data:`MAX_GAIN_DB`，保留两位小数。"""
    return round(min(TARGET_PEAK_DBFS - peak_dbfs, MAX_GAIN_DB), 2)


def _parse_sound(sfx_id: object, raw: object) -> SfxSound | None:
    if not is_sfx_id(sfx_id) or not isinstance(raw, Mapping):
        return None
    try:
        sound = SfxSound.model_validate({**raw, "id": sfx_id})
    except ValidationError:
        return None
    if sound.file not in {sfx_file_path(sound.id, extension) for extension in SFX_EXTENSIONS}:
        return None
    return sound


def read_sfx_library(project: Mapping[str, Any]) -> dict[str, SfxSound]:
    """``project.json`` 里登记的音效，按加入先后排列；形态不对的条目不计。"""
    bucket = project.get(PROJECT_SFX_FIELD)
    if not isinstance(bucket, Mapping):
        return {}
    sounds = (_parse_sound(sfx_id, raw) for sfx_id, raw in bucket.items())
    return {sound.id: sound for sound in sorted((s for s in sounds if s is not None), key=lambda s: s.added_at)}


def sfx_entry(sound: SfxSound) -> dict[str, object]:
    """写进 ``project.json`` 的形态：ID 是键，不重复存。"""
    return sound.model_dump(mode="json", exclude={"id"}, exclude_defaults=True)


def sfx_key(sfx_id: str) -> ArtifactKey:
    return ArtifactKey.project_sfx(sfx_id)


def sfx_basis(content_digest: str) -> ArtifactBasis:
    """音效的生成依据只有文件字节的内容指纹；登记与比对都经这里构造。"""
    return ArtifactBasis.build(SFX_BASIS_KIND, kind_version=SFX_BASIS_VERSION, inputs={"content": content_digest})


@dataclass(frozen=True, slots=True)
class SfxSource:
    """渲染读取的一个音效：项目内路径、正式文件当前字节的内容指纹，以及登记时缓存的静态增益。"""

    sfx_id: str
    path: str
    content_digest: str
    gain_db: float

    @property
    def gain(self) -> float:
        return 10 ** (self.gain_db / 20)

    def to_input(self) -> dict[str, object]:
        return {"content_digest": self.content_digest, "gain_db": self.gain_db}


def resolve_sfx_sources(
    project_dir: Path, project: Mapping[str, Any], sfx_ids: Collection[str], digest: Callable[[str], str]
) -> dict[str, SfxSource]:
    """``sfx_ids`` 里仍在项目里、文件在场的音效；``digest`` 按项目内路径取正式文件的内容指纹。"""
    library = read_sfx_library(project)
    sources: dict[str, SfxSource] = {}
    for sfx_id in sfx_ids:
        sound = library.get(sfx_id)
        if sound is None or not (project_dir / sound.file).is_file():
            continue
        sources[sfx_id] = SfxSource(
            sfx_id=sfx_id, path=sound.file, content_digest=digest(sound.file), gain_db=sound.gain_db
        )
    return sources


__all__ = [
    "MAX_GAIN_DB",
    "PROJECT_SFX_FIELD",
    "SFX_BASIS_KIND",
    "SFX_BASIS_VERSION",
    "SFX_DIR",
    "SFX_EXTENSIONS",
    "SFX_ID_PATTERN",
    "SFX_MAX_BYTES",
    "SFX_NAME_MAX_LENGTH",
    "SILENCE_PEAK_DBFS",
    "TARGET_PEAK_DBFS",
    "SfxOrigin",
    "SfxSound",
    "SfxSource",
    "is_sfx_id",
    "peak_gain_db",
    "read_sfx_library",
    "resolve_sfx_sources",
    "sfx_basis",
    "sfx_entry",
    "sfx_file_path",
    "sfx_key",
]
