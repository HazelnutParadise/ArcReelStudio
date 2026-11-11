"""search_stock_audio / import_stock_audio 工具：在免版权素材库里找音乐与音效，把选中的一条存进项目。"""

from __future__ import annotations

from pathlib import Path

import httpx2

from lib.bgm.service import BgmLibraryService
from lib.db.base import DEFAULT_USER_ID
from lib.project.project_manager import ProjectManager
from lib.sfx.service import SfxLibraryService
from server.agent_toolset.edit_timelines import IMPORT_STOCK_AUDIO, SEARCH_STOCK_AUDIO
from server.tool_runtime import CallerContext
from tests.factories import wav_bytes
from tests.http_capture import capture_http
from tests.integration.server.agent_tool_support import ToolHarness, run_declared_tool

_OPENVERSE_AUDIO = "https://api.openverse.org/v1/audio/"
_FREESOUND_SEARCH = "https://freesound.org/apiv2/search/text/"
# 档案地址用公网 IP 字面量：下载前的目的地校验不必解析主机名
_FILE_URL = "https://93.184.216.34/rain.wav"


def _harness(tmp_path: Path) -> ToolHarness:
    pm = ProjectManager(tmp_path)
    pm.create_project("demo")
    pm.create_project_metadata("demo", "Demo", "Anime", "narration")
    return ToolHarness("demo", tmp_path, pm, caller=CallerContext(user_id=DEFAULT_USER_ID, source="mcp"))


def _row(item_id: str, *, license_code: str = "cc0") -> dict:
    return {
        "id": item_id,
        "title": "Rain on a roof",
        "creator": "someone",
        "license": license_code,
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "foreign_landing_url": f"https://example.org/{item_id}",
        "url": _FILE_URL,
        "duration": 2000,
        "source": "wikimedia_audio",
    }


async def test_search_lists_items_and_says_which_sources_gave_nothing(tmp_path: Path) -> None:
    with capture_http() as router:
        router.get(_OPENVERSE_AUDIO).mock(return_value=httpx2.Response(200, json={"results": [_row("ov-1")]}))
        freesound = router.get(_FREESOUND_SEARCH).mock(return_value=httpx2.Response(200, json={"results": []}))
        found = await run_declared_tool(SEARCH_STOCK_AUDIO, _harness(tmp_path), {"kind": "sfx", "query": "rain"})

    assert found.problem is None
    assert [(item.source, item.id, item.duration, item.license) for item in found.value.items] == [
        ("openverse", "ov-1", 2.0, "cc0")
    ]
    # Freesound 的密钥属于成员，Agent 不代表某位成员，所以不会去问它
    assert found.value.unavailable == {"freesound": "key_missing"}
    assert not freesound.called
    assert SEARCH_STOCK_AUDIO.summary is not None
    assert "ov-1" in SEARCH_STOCK_AUDIO.summary(found.value)


async def test_import_stores_music_in_the_bgm_library_with_its_origin(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    with capture_http() as router:
        router.get(f"{_OPENVERSE_AUDIO}ov-1/").mock(return_value=httpx2.Response(200, json=_row("ov-1")))
        router.get(_FILE_URL).mock(return_value=httpx2.Response(200, content=wav_bytes(2.0, tone_hz=330)))
        imported = await run_declared_tool(
            IMPORT_STOCK_AUDIO, harness, {"kind": "music", "source": "openverse", "id": "ov-1"}
        )

    assert imported.problem is None
    (track,) = await BgmLibraryService(harness.pm).list("demo")
    assert (imported.value.kind, imported.value.id, imported.value.name) == ("music", track.id, "Rain on a roof")
    assert (track.source, track.license, track.source_url) == ("library", "cc0", "https://example.org/ov-1")
    assert IMPORT_STOCK_AUDIO.summary is not None
    assert "insert_bgm" in IMPORT_STOCK_AUDIO.summary(imported.value)


async def test_import_stores_a_sound_effect_in_the_sfx_library(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    with capture_http() as router:
        router.get(f"{_OPENVERSE_AUDIO}ov-2/").mock(return_value=httpx2.Response(200, json=_row("ov-2")))
        router.get(_FILE_URL).mock(return_value=httpx2.Response(200, content=wav_bytes(0.5, tone_hz=660)))
        imported = await run_declared_tool(
            IMPORT_STOCK_AUDIO, harness, {"kind": "sfx", "source": "openverse", "id": "ov-2"}
        )

    (sound,) = await SfxLibraryService(harness.pm).list("demo")
    assert (imported.value.kind, imported.value.id) == ("sfx", sound.id)
    assert sound.source == "library"


async def test_an_item_whose_license_needs_attribution_is_not_imported(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    with capture_http() as router:
        router.get(f"{_OPENVERSE_AUDIO}ov-3/").mock(
            return_value=httpx2.Response(200, json=_row("ov-3", license_code="by"))
        )
        imported = await run_declared_tool(
            IMPORT_STOCK_AUDIO, harness, {"kind": "music", "source": "openverse", "id": "ov-3"}
        )

    assert imported.problem is not None
    assert imported.problem.code == "stock_item_not_found"
    assert await BgmLibraryService(harness.pm).list("demo") == ()


async def test_a_member_keyed_source_is_refused_for_the_agent(tmp_path: Path) -> None:
    imported = await run_declared_tool(
        IMPORT_STOCK_AUDIO, _harness(tmp_path), {"kind": "sfx", "source": "freesound", "id": "1"}
    )

    assert imported.problem is not None
    assert imported.problem.code == "stock_key_missing"
