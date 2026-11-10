"""音效登记：在真实临时项目上用随包 ffmpeg 实测峰值，按字节登记为项目级产物。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.artifacts.artifact_activation import ArtifactCurrencyResolver
from lib.artifacts.artifact_manifest import ArtifactStatus
from lib.project.project_manager import ProjectManager
from lib.sfx.library import TARGET_PEAK_DBFS, sfx_entry, sfx_key
from lib.sfx.service import SfxError, SfxLibraryService
from tests.factories import wav_bytes


@pytest.fixture
def sfx_pm(tmp_path: Path) -> ProjectManager:
    manager = ProjectManager(str(tmp_path / "projects"))
    manager.create_project("demo")
    manager.create_project_metadata("demo", "Demo", "Anime", "narration")
    return manager


def _sfx_leftovers(manager: ProjectManager) -> list[str]:
    sfx_dir = manager.get_project_path("demo") / "sfx"
    return sorted(path.name for path in sfx_dir.iterdir()) if sfx_dir.exists() else []


async def test_upload_measures_the_peak_and_registers_the_bytes(sfx_pm: ProjectManager) -> None:
    service = SfxLibraryService(sfx_pm)

    sound = await service.upload("demo", filename="关门.wav", content=wav_bytes(0.5, tone_hz=440))

    project_dir = sfx_pm.get_project_path("demo")
    assert sound.name == "关门"
    assert sound.file == f"sfx/{sound.id}.wav"
    assert sound.duration == pytest.approx(0.5, abs=0.01)
    assert -40 < sound.peak_dbfs <= 0
    assert sound.gain_db == pytest.approx(TARGET_PEAK_DBFS - sound.peak_dbfs, abs=0.01)
    stored = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))["sfx"]
    assert stored == {sound.id: sfx_entry(sound)}
    assert await service.list("demo") == (sound,)
    assert _sfx_leftovers(sfx_pm) == [f"{sound.id}.wav"]
    status = ArtifactCurrencyResolver(project_dir).compare(sfx_key(sound.id), artifact_path=sound.file).status
    assert status is ArtifactStatus.CURRENT


async def test_generated_sounds_record_their_origin(sfx_pm: ProjectManager) -> None:
    sound = await SfxLibraryService(sfx_pm).register_generated(
        "demo",
        name="玻璃碎裂",
        extension=".WAV",
        content=wav_bytes(0.8, tone_hz=660),
        prompt="glass shattering",
        model="elevenlabs/eleven_text_to_sound_v3",
    )

    assert (sound.source, sound.prompt, sound.model) == ("ai", "glass shattering", "elevenlabs/eleven_text_to_sound_v3")
    assert sound.file == f"sfx/{sound.id}.wav"


@pytest.mark.parametrize(
    ("filename", "content", "code"),
    [
        ("silence.wav", wav_bytes(0.5), "sfx_silent"),
        ("broken.mp3", b"not audio at all", "sfx_invalid_audio"),
        ("cover.png", wav_bytes(0.5, tone_hz=330), "sfx_unsupported_type"),
    ],
)
async def test_unusable_sounds_are_refused_without_leaving_files(
    sfx_pm: ProjectManager, filename: str, content: bytes, code: str
) -> None:
    service = SfxLibraryService(sfx_pm)

    with pytest.raises(SfxError) as refused:
        await service.upload("demo", filename=filename, content=content)

    assert refused.value.code == code
    assert _sfx_leftovers(sfx_pm) == []
    assert await service.list("demo") == ()
