"""BGM 与音效共用一条登记流程：每种失败都报成各库自己的错误码，且不留下任何文件。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, get_args

import pytest

from lib.audio_library.service import AudioErrorKind, AudioLibraryKind, AudioLibraryService
from lib.bgm.service import BGM_LIBRARY, BgmError, BgmLibraryService
from lib.infra.ffmpeg import FfmpegUnavailableError
from lib.project.project_manager import ProjectManager
from lib.sfx.service import SFX_LIBRARY, SfxError, SfxLibraryService
from tests.factories import wav_bytes


@dataclass(frozen=True)
class _Library:
    kind: AudioLibraryKind[Any]
    service: Callable[[ProjectManager], AudioLibraryService[Any]]
    error: type[Exception]
    prefix: str


LIBRARIES = [
    pytest.param(_Library(BGM_LIBRARY, BgmLibraryService, BgmError, "bgm"), id="bgm"),
    pytest.param(_Library(SFX_LIBRARY, SfxLibraryService, SfxError, "sfx"), id="sfx"),
]


@pytest.fixture
def pm(tmp_path: Path) -> ProjectManager:
    manager = ProjectManager(str(tmp_path / "projects"))
    manager.create_project("demo")
    manager.create_project_metadata("demo", "Demo", "Anime", "narration")
    return manager


def _leftovers(manager: ProjectManager, directory: str) -> list[str]:
    library_dir = manager.get_project_path("demo") / directory
    return sorted(path.name for path in library_dir.iterdir()) if library_dir.exists() else []


def _expected_code(kind: str, prefix: str) -> str:
    return kind if kind == "project_not_found" else f"{prefix}_{kind}"


@pytest.mark.parametrize("library", LIBRARIES)
@pytest.mark.parametrize("kind", get_args(AudioErrorKind.__value__))
def test_every_failure_kind_maps_to_the_library_own_code(library: _Library, kind: str) -> None:
    error = library.kind.error(kind, "message")

    assert isinstance(error, library.error)
    assert error.code == _expected_code(kind, library.prefix)


@pytest.mark.parametrize("library", LIBRARIES)
async def test_unknown_project_is_reported_with_the_library_error(pm: ProjectManager, library: _Library) -> None:
    with pytest.raises(library.error) as refused:
        await library.service(pm).list("missing")

    assert refused.value.code == "project_not_found"


@pytest.mark.parametrize("library", LIBRARIES)
async def test_too_large_files_are_refused_without_leaving_files(pm: ProjectManager, library: _Library) -> None:
    content = wav_bytes(1.0)
    service = AudioLibraryService(replace(library.kind, max_bytes=len(content) - 1), pm)

    with pytest.raises(library.error) as refused:
        await service.upload("demo", filename="clip.wav", content=content)

    assert refused.value.code == f"{library.prefix}_too_large"
    assert _leftovers(pm, library.kind.directory) == []
    assert await service.list("demo") == ()


@pytest.mark.parametrize("library", LIBRARIES)
async def test_missing_ffmpeg_is_reported_without_leaving_files(
    pm: ProjectManager, library: _Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable() -> str:
        raise FfmpegUnavailableError("ffmpeg is missing")

    monkeypatch.setattr("lib.audio_library.service.ffmpeg_executable", unavailable)
    service = library.service(pm)

    with pytest.raises(library.error) as refused:
        await service.upload("demo", filename="clip.wav", content=wav_bytes(1.0, tone_hz=440))

    assert refused.value.code == f"{library.prefix}_ffmpeg_unavailable"
    assert _leftovers(pm, library.kind.directory) == []
    assert await service.list("demo") == ()
