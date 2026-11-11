"""音效命令：上传与 AI 生成音效的登记、列出；HTTP、Agent 工具与生成任务共用。

登记时先把字节写进 ``sfx/`` 下的隐藏暂存文件，探测出音频时长、实测峰值后，在 ``project.json`` 的同一次原子更新里
落正式文件、写元数据并按字节登记产物；任何一步失败，正式文件、元数据与登记都不留下。登记后的音效不能替换或删除。
"""

from __future__ import annotations

import asyncio
import secrets
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from lib.artifacts.artifact_registration import register_current_artifact
from lib.infra.async_thread import run_sync_transaction
from lib.infra.content_digest import sha256_file
from lib.infra.ffmpeg import FfmpegUnavailableError, ffmpeg_executable
from lib.infra.media_probe import MediaProbeError, probe_media
from lib.infra.subprocess_deadline import Spawner
from lib.project.project_change_hints import project_change_source
from lib.project.project_manager import ProjectManager
from lib.sfx.library import (
    PROJECT_SFX_FIELD,
    SFX_DIR,
    SFX_EXTENSIONS,
    SFX_MAX_BYTES,
    SFX_NAME_MAX_LENGTH,
    SILENCE_PEAK_DBFS,
    SfxOrigin,
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


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sfx_display_name(filename: str) -> str:
    """音效的显示名取文件名去掉扩展名，过长截断；取不出时为「音效」。"""
    stem = unicodedata.normalize("NFC", Path(filename).stem).strip()
    return stem[:SFX_NAME_MAX_LENGTH].strip() or "音效"


class SfxLibraryService:
    def __init__(self, projects: ProjectManager, *, spawn: Spawner | None = None) -> None:
        self._projects = projects
        self._spawn = spawn

    def _project_dir(self, project_name: str) -> Path:
        if not self._projects.project_exists(project_name):
            raise SfxError("project_not_found", f"项目「{project_name}」不存在", project=project_name)
        return self._projects.get_project_path(project_name)

    async def list(self, project_name: str) -> tuple[SfxSound, ...]:
        """项目里已登记的音效，按加入先后排列。"""
        project = await asyncio.to_thread(self._load_project, project_name)
        return tuple(read_sfx_library(project).values())

    def _load_project(self, project_name: str) -> dict[str, Any]:
        self._project_dir(project_name)
        return self._projects.load_project(project_name)

    async def upload(self, project_name: str, *, filename: str, content: bytes) -> SfxSound:
        """登记一个使用者上传的音效。"""
        return await self._register(
            project_name, name=sfx_display_name(filename), extension=Path(filename).suffix.lower(), content=content
        )

    async def register_generated(
        self, project_name: str, *, name: str, extension: str, content: bytes, prompt: str, model: str
    ) -> SfxSound:
        """登记一个 AI 生成的音效：与上传走同一条登记，并记下提示词与生成它的 ``provider/model``。"""
        return await self._register(
            project_name,
            name=sfx_display_name(name),
            extension=extension.lower(),
            content=content,
            source="ai",
            prompt=prompt,
            model=model,
        )

    async def register_library(
        self, project_name: str, *, name: str, extension: str, content: bytes, license: str, source_url: str
    ) -> SfxSound:
        """登记一条从免版权素材库导入的音效：与上传走同一条登记，并记下授权与它在来源站的页面。"""
        return await self._register(
            project_name,
            name=sfx_display_name(name),
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
        source: SfxOrigin = "upload",
        prompt: str | None = None,
        model: str | None = None,
        license: str | None = None,
        source_url: str | None = None,
    ) -> SfxSound:
        project_dir = await asyncio.to_thread(self._project_dir, project_name)
        if extension not in SFX_EXTENSIONS:
            raise SfxError(
                "sfx_unsupported_type",
                f"音效只支持 {', '.join(SFX_EXTENSIONS)}，收到 {extension or '无扩展名'}",
                ext=extension,
                allowed=", ".join(SFX_EXTENSIONS),
            )
        if len(content) > SFX_MAX_BYTES:
            raise SfxError("sfx_too_large", "音效文件过大", max_mb=SFX_MAX_BYTES // (1024 * 1024))
        try:
            ffmpeg = await asyncio.to_thread(ffmpeg_executable)
        except FfmpegUnavailableError as exc:
            raise SfxError("sfx_ffmpeg_unavailable", f"随包 ffmpeg 不可用，无法测量音效峰值：{exc}") from exc
        sfx_dir = project_dir / SFX_DIR
        sfx_id = f"sfx-{secrets.token_hex(4)}"
        staged = sfx_dir / f".{sfx_id}.{secrets.token_hex(4)}.upload{extension}"
        await asyncio.to_thread(sfx_dir.mkdir, exist_ok=True)
        try:
            await run_sync_transaction(staged.write_bytes, content)
            duration_us = await self._duration_us(staged)
            peak = await self._peak(ffmpeg, staged, duration_us)
            sound = SfxSound(
                id=sfx_id,
                name=name,
                file=sfx_file_path(sfx_id, extension),
                duration_us=duration_us,
                peak_dbfs=round(peak, 2),
                gain_db=peak_gain_db(peak),
                content_digest=await asyncio.to_thread(sha256_file, staged),
                added_at=_utc_now(),
                source=source,
                prompt=prompt,
                model=model,
                license=license,
                source_url=source_url,
            )
            await run_sync_transaction(self._commit, project_name, project_dir, staged, sound)
        finally:
            await asyncio.to_thread(staged.unlink, missing_ok=True)  # hard-delete: temp -- 登记暂存文件
        return sound

    async def _duration_us(self, path: Path) -> int:
        try:
            probe = await probe_media(path, spawn=self._spawn)
        except MediaProbeError as exc:
            raise SfxError("sfx_invalid_audio", f"音效文件无法解析：{exc}") from exc
        audio = probe.first_stream("audio")
        duration = audio.duration_seconds if audio is not None else None
        if duration is None or duration <= 0:
            raise SfxError("sfx_invalid_audio", "音效文件里没有可用的音频")
        return round(duration * 1_000_000)

    async def _peak(self, ffmpeg: str, path: Path, duration_us: int) -> float:
        try:
            peak = await measure_peak(ffmpeg, path, duration_seconds=duration_us / 1_000_000, spawn=self._spawn)
        except PeakMeasurementError as exc:
            raise SfxError("sfx_invalid_audio", f"音效的峰值测不出来：{exc}") from exc
        if peak <= SILENCE_PEAK_DBFS:
            raise SfxError("sfx_silent", "音效几乎没有声音，测不出可用的峰值")
        return peak

    def _commit(self, project_name: str, project_dir: Path, staged: Path, sound: SfxSound) -> None:
        target = project_dir / sound.file

        def mutate(project: dict) -> None:
            bucket = project.get(PROJECT_SFX_FIELD)
            if not isinstance(bucket, dict):
                bucket = project[PROJECT_SFX_FIELD] = {}
            if sound.id in bucket:
                raise RuntimeError(f"音效 ID 已被占用：{sound.id}")
            bucket[sound.id] = sfx_entry(sound)

        def install(_project_file: Path) -> None:
            staged.replace(target)
            register_current_artifact(
                project_dir, sfx_key(sound.id), artifact_path=sound.file, basis=sfx_basis(sound.content_digest)
            )

        with project_change_source("webui"):
            self._projects.update_project(project_name, mutate, on_commit=install, formal_paths=(target,))


__all__ = ["SfxError", "SfxErrorCode", "SfxLibraryService", "sfx_display_name"]
