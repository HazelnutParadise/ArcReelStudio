"""项目级音频库（BGM、音效）共用的登记流程（``docs/adr/0127``）；HTTP、Agent 工具与生成任务共用。

登记时先把字节写进库目录下的隐藏暂存文件，探测出音频时长、实测电平后，在 ``project.json`` 的同一次原子更新里
落正式文件、写元数据并按字节登记产物；任何一步失败，正式文件、元数据与登记都不留下。登记后的条目不能替换或删除。

各库只用 :class:`AudioLibraryKind` 声明自己的差异：目录与字段、格式与大小上限、测哪种电平、条目存哪些栏位、
错误码与提示文字。流程本身只有这一份。
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from lib.artifacts.artifact_manifest import ArtifactBasis, ArtifactKey
from lib.artifacts.artifact_registration import register_current_artifact
from lib.audio_library.library import AudioItem, audio_display_name
from lib.infra.async_thread import run_sync_transaction
from lib.infra.content_digest import sha256_file
from lib.infra.ffmpeg import FfmpegUnavailableError, ffmpeg_executable
from lib.infra.media_probe import MediaProbeError, probe_media
from lib.infra.subprocess_deadline import Spawner
from lib.project.project_change_hints import project_change_source
from lib.project.project_manager import ProjectManager

type AudioErrorKind = Literal[
    "project_not_found",
    "unsupported_type",
    "too_large",
    "invalid_audio",
    "silent",
    "ffmpeg_unavailable",
]
type AudioOrigin = Literal["upload", "ai", "library"]


class AudioErrorFactory(Protocol):
    """把共用的错误种类换成各库自己的异常（各库的错误码不同，适配器按它映射）。"""

    def __call__(self, kind: AudioErrorKind, message: str, /, **params: Any) -> Exception: ...


class LevelMeter(Protocol):
    """实测一个音频文件的电平；测不出时抛出 :attr:`AudioLibraryKind.measurement_error`。"""

    async def __call__(
        self, ffmpeg: str, path: Path, *, duration_seconds: float, spawn: Spawner | None = None
    ) -> float: ...


@dataclass(frozen=True, kw_only=True)
class AudioMessages:
    """各库的提示文字。``{allowed}`` 是允许的扩展名，``{got}`` 是收到的扩展名，``{detail}`` 是底层错误，``{id}`` 是条目 ID。"""

    unsupported_type: str
    too_large: str
    ffmpeg_unavailable: str
    unparsable: str
    no_audio: str
    unmeasurable: str
    silent: str
    duplicate_id: str


@dataclass(frozen=True, kw_only=True)
class AudioDraft:
    """登记流程量出来的一切；各库把它换成自己的条目（栏位名与增益算法各不相同）。"""

    id: str
    name: str
    file: str
    duration_us: int
    level: float
    """实测电平：BGM 是积分响度（LUFS），音效是峰值（dBFS）。"""
    content_digest: str
    registered_at: str
    source: AudioOrigin
    prompt: str | None
    model: str | None
    license: str | None
    source_url: str | None


@dataclass(frozen=True, kw_only=True)
class AudioLibraryKind[Item: AudioItem]:
    """一个音频库与其他库不同的地方。"""

    id_prefix: str
    directory: str
    project_field: str
    extensions: tuple[str, ...]
    max_bytes: int
    name_max_length: int
    fallback_name: str
    file_path: Callable[[str, str], str]
    measure_level: LevelMeter
    measurement_error: type[Exception]
    silence_threshold: float
    """实测电平不高于它就当作几乎无声，折算不出可用的增益。"""
    build: Callable[[AudioDraft], Item]
    entry: Callable[[Item], dict[str, object]]
    key: Callable[[str], ArtifactKey]
    basis: Callable[[str], ArtifactBasis]
    read: Callable[[Mapping[str, Any]], dict[str, Item]]
    error: AudioErrorFactory
    messages: AudioMessages


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class AudioLibraryService[Item: AudioItem]:
    def __init__(self, kind: AudioLibraryKind[Item], projects: ProjectManager, *, spawn: Spawner | None = None) -> None:
        self._kind = kind
        self._projects = projects
        self._spawn = spawn

    def _display_name(self, filename: str) -> str:
        return audio_display_name(filename, max_length=self._kind.name_max_length, fallback=self._kind.fallback_name)

    def _project_dir(self, project_name: str) -> Path:
        if not self._projects.project_exists(project_name):
            raise self._kind.error("project_not_found", f"项目「{project_name}」不存在", project=project_name)
        return self._projects.get_project_path(project_name)

    async def list(self, project_name: str) -> tuple[Item, ...]:
        """项目里已登记的条目，按加入先后排列。"""
        project = await asyncio.to_thread(self._load_project, project_name)
        return tuple(self._kind.read(project).values())

    def _load_project(self, project_name: str) -> dict[str, Any]:
        self._project_dir(project_name)
        return self._projects.load_project(project_name)

    async def upload(self, project_name: str, *, filename: str, content: bytes) -> Item:
        """登记一个使用者上传的文件：校验格式与大小，探测时长，实测电平并折算增益，原子落盘并按字节登记。"""
        return await self._register(
            project_name, name=self._display_name(filename), extension=Path(filename).suffix.lower(), content=content
        )

    async def register_generated(
        self, project_name: str, *, name: str, extension: str, content: bytes, prompt: str, model: str
    ) -> Item:
        """登记一个 AI 生成的文件：与上传走同一条登记，并记下提示词与生成它的 ``provider/model``。"""
        return await self._register(
            project_name,
            name=self._display_name(name),
            extension=extension.lower(),
            content=content,
            source="ai",
            prompt=prompt,
            model=model,
        )

    async def register_library(
        self, project_name: str, *, name: str, extension: str, content: bytes, license: str, source_url: str
    ) -> Item:
        """登记一条从免版权素材库导入的文件：与上传走同一条登记，并记下授权与它在来源站的页面。"""
        return await self._register(
            project_name,
            name=self._display_name(name),
            extension=extension.lower(),
            content=content,
            source="library",
            license=license,
            source_url=source_url,
        )

    async def _register(
        self,
        project_name: str,
        *,
        name: str,
        extension: str,
        content: bytes,
        source: AudioOrigin = "upload",
        prompt: str | None = None,
        model: str | None = None,
        license: str | None = None,
        source_url: str | None = None,
    ) -> Item:
        kind = self._kind
        messages = kind.messages
        project_dir = await asyncio.to_thread(self._project_dir, project_name)
        if extension not in kind.extensions:
            allowed = ", ".join(kind.extensions)
            raise kind.error(
                "unsupported_type",
                messages.unsupported_type.format(allowed=allowed, got=extension or "无扩展名"),
                ext=extension,
                allowed=allowed,
            )
        if len(content) > kind.max_bytes:
            raise kind.error("too_large", messages.too_large, max_mb=kind.max_bytes // (1024 * 1024))
        try:
            ffmpeg = await asyncio.to_thread(ffmpeg_executable)
        except FfmpegUnavailableError as exc:
            raise kind.error("ffmpeg_unavailable", messages.ffmpeg_unavailable.format(detail=exc)) from exc
        library_dir = project_dir / kind.directory
        item_id = f"{kind.id_prefix}-{secrets.token_hex(4)}"
        staged = library_dir / f".{item_id}.{secrets.token_hex(4)}.upload{extension}"
        await asyncio.to_thread(library_dir.mkdir, exist_ok=True)
        try:
            await run_sync_transaction(staged.write_bytes, content)
            duration_us = await self._duration_us(staged)
            level = await self._level(ffmpeg, staged, duration_us)
            item = kind.build(
                AudioDraft(
                    id=item_id,
                    name=name,
                    file=kind.file_path(item_id, extension),
                    duration_us=duration_us,
                    level=level,
                    content_digest=await asyncio.to_thread(sha256_file, staged),
                    registered_at=_utc_now(),
                    source=source,
                    prompt=prompt,
                    model=model,
                    license=license,
                    source_url=source_url,
                )
            )
            await run_sync_transaction(self._commit, project_name, project_dir, staged, item)
        finally:
            await asyncio.to_thread(staged.unlink, missing_ok=True)  # hard-delete: temp -- 登记暂存文件
        return item

    async def _duration_us(self, path: Path) -> int:
        messages = self._kind.messages
        try:
            probe = await probe_media(path, spawn=self._spawn)
        except MediaProbeError as exc:
            raise self._kind.error("invalid_audio", messages.unparsable.format(detail=exc)) from exc
        audio = probe.first_stream("audio")
        duration = audio.duration_seconds if audio is not None else None
        if duration is None or duration <= 0:
            raise self._kind.error("invalid_audio", messages.no_audio)
        return round(duration * 1_000_000)

    async def _level(self, ffmpeg: str, path: Path, duration_us: int) -> float:
        kind = self._kind
        try:
            level = await kind.measure_level(ffmpeg, path, duration_seconds=duration_us / 1_000_000, spawn=self._spawn)
        except kind.measurement_error as exc:
            raise kind.error("invalid_audio", kind.messages.unmeasurable.format(detail=exc)) from exc
        if level <= kind.silence_threshold:
            raise kind.error("silent", kind.messages.silent)
        return level

    def _commit(self, project_name: str, project_dir: Path, staged: Path, item: Item) -> None:
        kind = self._kind
        target = project_dir / item.file

        def mutate(project: dict) -> None:
            bucket = project.get(kind.project_field)
            if not isinstance(bucket, dict):
                bucket = project[kind.project_field] = {}
            if item.id in bucket:
                raise RuntimeError(kind.messages.duplicate_id.format(id=item.id))
            bucket[item.id] = kind.entry(item)

        def install(_project_file: Path) -> None:
            staged.replace(target)
            register_current_artifact(
                project_dir, kind.key(item.id), artifact_path=item.file, basis=kind.basis(item.content_digest)
            )

        with project_change_source("webui"):
            self._projects.update_project(project_name, mutate, on_commit=install, formal_paths=(target,))


__all__ = [
    "AudioDraft",
    "AudioErrorFactory",
    "AudioErrorKind",
    "AudioLibraryKind",
    "AudioLibraryService",
    "AudioMessages",
    "AudioOrigin",
    "LevelMeter",
]
