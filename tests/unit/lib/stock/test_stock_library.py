"""免版权素材库：各来源只放行免署名的授权，搜索合并各来源并报告状态，下载只走公网 HTTPS。"""

from __future__ import annotations

from collections.abc import Iterable

import httpx2
import pytest

from lib.backends.artifact_download_guard import ArtifactTooLargeError
from lib.stock.model import StockError
from lib.stock.service import (
    STOCK_FILE_MAX_BYTES,
    StockLibraryService,
    check_public_destination,
    download_public,
    stock_file_name,
)
from lib.stock.sources import STOCK_SOURCES
from tests.http_capture import capture_http, only_request

_OPENVERSE_AUDIO = "https://api.openverse.org/v1/audio/"
_OPENVERSE_IMAGES = "https://api.openverse.org/v1/images/"
_PIXABAY = "https://pixabay.com/api/"
_PEXELS_SEARCH = "https://api.pexels.com/v1/search"
_FREESOUND_SEARCH = "https://freesound.org/apiv2/search/text/"


async def _plain_download(url: str) -> bytes:
    async with httpx2.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url)
        declared = int(response.headers.get("Content-Length", "0"))
        if declared > STOCK_FILE_MAX_BYTES:
            raise ArtifactTooLargeError("too large")
        return response.content


def _service() -> StockLibraryService:
    # 下载端不接公网校验：测试里的主机名解析不到公网地址，校验与连到校验过的地址另有用例。
    return StockLibraryService(download=_plain_download)


def _openverse_audio(item_id: str, *, license_code: str = "cc0", source: str = "jamendo", ext: str = "mp3") -> dict:
    return {
        "id": item_id,
        "title": f"Track {item_id}",
        "creator": "Someone",
        "license": license_code,
        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "foreign_landing_url": f"https://example.org/tracks/{item_id}",
        "url": f"https://cdn.example.org/{item_id}.{ext}",
        "duration": 61500,
        "source": source,
    }


def _pixabay_hit(item_id: int) -> dict:
    return {
        "id": item_id,
        "tags": "city, night",
        "user": "shooter",
        "pageURL": f"https://pixabay.com/photos/{item_id}/",
        "webformatURL": f"https://pixabay.com/get/{item_id}_640.jpg",
        "largeImageURL": f"https://pixabay.com/get/{item_id}_1280.jpg",
        "imageWidth": 4000,
        "imageHeight": 3000,
    }


def _freesound_row(item_id: int, license_text: str) -> dict:
    return {
        "id": item_id,
        "name": "door slam",
        "username": "recordist",
        "license": license_text,
        "url": f"https://freesound.org/people/recordist/sounds/{item_id}/",
        "duration": 1.25,
        "previews": {"preview-hq-mp3": f"https://cdn.freesound.org/previews/{item_id}-hq.mp3"},
    }


async def test_openverse_music_search_asks_for_public_domain_only_and_drops_anything_else() -> None:
    rows = [
        _openverse_audio("a"),
        _openverse_audio("b", license_code="by"),
        _openverse_audio("c", source="freesound"),
        _openverse_audio("d", ext="mid"),
        _openverse_audio("e", license_code="pdm", ext="ogg"),
        {**_openverse_audio("f"), "duration": 1200},
    ]
    with capture_http() as router:
        route = router.get(_OPENVERSE_AUDIO).mock(return_value=httpx2.Response(200, json={"results": rows}))
        result = await _service().search(kind="music", query="calm piano", page=2, keys={})

    params = only_request(route).url.params
    assert params["license"] == "cc0,pdm"
    assert "category" not in params
    assert "ogg" in params["extension"]
    assert params["excluded_source"] == "freesound"
    assert params["page"] == "2"
    assert [item.id for item in result.items] == ["a", "e"]
    first = result.items[0]
    assert (first.source, first.kind, first.license, first.duration_seconds) == ("openverse", "music", "cc0", 61.5)
    assert first.preview_url == "https://cdn.example.org/a.mp3"
    assert [(entry.source, entry.status) for entry in result.sources] == [
        ("openverse", "ok"),
        ("freesound", "key_missing"),
    ]


async def test_image_search_merges_sources_in_turn_and_reports_a_source_without_a_key() -> None:
    openverse_rows = [
        {
            "id": f"ov-{index}",
            "title": "old map",
            "license": "pdm",
            "license_url": "https://creativecommons.org/publicdomain/mark/1.0/",
            "foreign_landing_url": "https://example.org/map",
            "url": f"https://cdn.example.org/map-{index}.jpg",
            "thumbnail": f"https://api.openverse.org/v1/images/ov-{index}/thumb/",
            "width": 800,
            "height": 600,
        }
        for index in range(2)
    ]
    with capture_http() as router:
        router.get(_OPENVERSE_IMAGES).mock(return_value=httpx2.Response(200, json={"results": openverse_rows}))
        pixabay = router.get(_PIXABAY).mock(return_value=httpx2.Response(200, json={"hits": [_pixabay_hit(7)]}))
        result = await _service().search(kind="image", query="map", page=1, keys={"pixabay": "pix-key"})

    assert only_request(pixabay).url.params["key"] == "pix-key"
    assert [(item.source, item.id) for item in result.items] == [
        ("openverse", "ov-0"),
        ("pixabay", "7"),
        ("openverse", "ov-1"),
    ]
    assert {entry.source: entry.status for entry in result.sources} == {
        "openverse": "ok",
        "pixabay": "ok",
        "pexels": "key_missing",
    }
    pixabay_item = result.items[1]
    assert (pixabay_item.license, pixabay_item.creator) == ("pixabay", "shooter")
    assert pixabay_item.preview_url == "https://pixabay.com/get/7_640.jpg"


async def test_one_failing_source_does_not_hide_the_others() -> None:
    with capture_http() as router:
        router.get(_OPENVERSE_IMAGES).mock(return_value=httpx2.Response(503))
        router.get(_PIXABAY).mock(return_value=httpx2.Response(200, json={"hits": [_pixabay_hit(1)]}))
        router.get(_PEXELS_SEARCH).mock(return_value=httpx2.Response(401))
        result = await _service().search(
            kind="image", query="sea", page=1, keys={"pixabay": "pix-key", "pexels": "bad-key"}
        )

    assert [item.id for item in result.items] == ["1"]
    assert {entry.source: entry.status for entry in result.sources} == {
        "openverse": "failed",
        "pixabay": "ok",
        "pexels": "key_rejected",
    }


async def test_freesound_uses_the_members_token_and_keeps_only_cc0() -> None:
    rows = [
        _freesound_row(1, "https://creativecommons.org/publicdomain/zero/1.0/"),
        _freesound_row(2, "https://creativecommons.org/licenses/by/4.0/"),
        _freesound_row(3, "Creative Commons 0"),
    ]
    with capture_http() as router:
        route = router.get(_FREESOUND_SEARCH).mock(return_value=httpx2.Response(200, json={"results": rows}))
        result = await _service().search(kind="sfx", query="door", page=1, keys={"freesound": "member-token"})

    sent = only_request(route)
    assert sent.headers["Authorization"] == "Token member-token"
    assert sent.url.params["filter"] == 'license:"Creative Commons 0"'
    assert [(item.source, item.id, item.license) for item in result.items] == [
        ("freesound", "1", "cc0"),
        ("freesound", "3", "cc0"),
    ]


async def test_fetch_resolves_the_item_again_by_id_and_downloads_from_the_sources_address() -> None:
    with capture_http() as router:
        resolve = router.get(_PIXABAY).mock(return_value=httpx2.Response(200, json={"hits": [_pixabay_hit(9)]}))
        router.get("https://pixabay.com/get/9_1280.jpg").mock(return_value=httpx2.Response(200, content=b"JPEGDATA"))
        file = await _service().fetch(source_id="pixabay", kind="image", item_id="9", key="pix-key")

    assert only_request(resolve).url.params["id"] == "9"
    assert "ArcReelStudio" in only_request(resolve).headers["User-Agent"]
    assert (file.item.id, file.extension, file.content) == ("9", ".jpg", b"JPEGDATA")


async def test_fetch_refuses_an_item_whose_license_is_out_of_range() -> None:
    with capture_http() as router:
        router.get(f"{_OPENVERSE_AUDIO}x1/").mock(
            return_value=httpx2.Response(200, json=_openverse_audio("x1", license_code="by-nc"))
        )
        with pytest.raises(StockError) as caught:
            await _service().fetch(source_id="openverse", kind="music", item_id="x1", key=None)

    assert caught.value.code == "stock_item_not_found"


async def test_fetch_stops_at_the_size_limit() -> None:
    with capture_http() as router:
        router.get(_PIXABAY).mock(return_value=httpx2.Response(200, json={"hits": [_pixabay_hit(9)]}))
        router.get("https://pixabay.com/get/9_1280.jpg").mock(
            return_value=httpx2.Response(200, content=b"x", headers={"Content-Length": str(STOCK_FILE_MAX_BYTES + 1)})
        )
        with pytest.raises(StockError) as caught:
            await _service().fetch(source_id="pixabay", kind="image", item_id="9", key="pix-key")

    assert caught.value.code == "stock_file_too_large"


async def test_a_source_is_refused_for_a_kind_it_does_not_provide() -> None:
    with pytest.raises(StockError) as caught:
        await _service().resolve(source_id="pixabay", kind="music", item_id="1", key="pix-key")
    assert caught.value.code == "stock_kind_unsupported"

    with pytest.raises(StockError) as unknown:
        await _service().resolve(source_id="nowhere", kind="music", item_id="1", key=None)
    assert unknown.value.code == "stock_unknown_source"


@pytest.mark.parametrize(
    ("url", "addresses"),
    [
        ("http://cdn.example.org/a.mp3", ["93.184.216.34"]),
        ("https://internal.example.org/a.mp3", ["10.0.0.5"]),
        ("https://localhost/a.mp3", ["127.0.0.1"]),
        ("https://metadata.example.org/a.mp3", ["169.254.169.254"]),
        ("https://mixed.example.org/a.mp3", ["93.184.216.34", "192.168.1.1"]),
        ("https://192.168.0.10/a.mp3", []),
        ("https://nat64.example.org/a.mp3", ["64:ff9b::7f00:1"]),
        ("https://compat.example.org/a.mp3", ["::127.0.0.1"]),
        ("https://mapped.example.org/a.mp3", ["::ffff:10.0.0.1"]),
    ],
)
async def test_downloads_are_refused_unless_the_destination_is_public_https(url: str, addresses: list[str]) -> None:
    async def resolver(_host: str, _port: int) -> Iterable[str]:
        return addresses

    with pytest.raises(StockError) as caught:
        await check_public_destination(httpx2.URL(url), resolver=resolver)
    assert caught.value.code == "stock_download_rejected"


async def test_a_public_https_destination_passes_and_an_unresolvable_host_is_refused() -> None:
    async def public(_host: str, _port: int) -> Iterable[str]:
        return ["93.184.216.34"]

    async def broken(_host: str, _port: int) -> Iterable[str]:
        raise OSError("no such host")

    await check_public_destination(httpx2.URL("https://cdn.example.org/a.mp3"), resolver=public)
    with pytest.raises(StockError):
        await check_public_destination(httpx2.URL("https://cdn.example.org/a.mp3"), resolver=broken)


def test_every_source_declares_what_it_provides_and_whose_key_it_needs() -> None:
    assert {source_id: (sorted(source.kinds), source.key_scope) for source_id, source in STOCK_SOURCES.items()} == {
        "openverse": (["image", "music"], "none"),
        "pixabay": (["image"], "workspace"),
        "pexels": (["image"], "workspace"),
        "freesound": (["music", "sfx"], "member"),
    }


async def test_freesound_music_search_asks_for_longer_recordings() -> None:
    with capture_http() as router:
        router.get(_OPENVERSE_AUDIO).mock(return_value=httpx2.Response(200, json={"results": []}))
        route = router.get(_FREESOUND_SEARCH).mock(
            return_value=httpx2.Response(200, json={"results": [_freesound_row(5, "Creative Commons 0")]})
        )
        result = await _service().search(kind="music", query="loop", page=1, keys={"freesound": "member-token"})

    assert only_request(route).url.params["filter"] == 'license:"Creative Commons 0" duration:[15 TO *]'
    assert [(item.source, item.kind) for item in result.items] == [("freesound", "music")]


async def test_openverse_offers_no_sound_effects() -> None:
    with pytest.raises(StockError) as caught:
        await _service().resolve(source_id="openverse", kind="sfx", item_id="x", key=None)
    assert caught.value.code == "stock_kind_unsupported"


def _recording_client(handler):
    return lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


async def test_a_download_connects_to_the_address_that_was_checked() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, content=b"AUDIO")

    async def resolver(_host: str, _port: int) -> Iterable[str]:
        return ["93.184.216.34"]

    content = await download_public(
        "https://cdn.example.org/a.mp3?x=1", resolver=resolver, client=_recording_client(handler)
    )

    assert content == b"AUDIO"
    (request,) = seen
    assert str(request.url) == "https://93.184.216.34/a.mp3?x=1"
    assert request.headers["Host"] == "cdn.example.org"
    assert request.extensions["sni_hostname"] == "cdn.example.org"


async def test_a_redirect_to_a_private_address_is_refused_before_connecting() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers["Host"])
        return httpx2.Response(302, headers={"Location": "https://internal.example.org/secret"})

    async def resolver(host: str, _port: int) -> Iterable[str]:
        return ["10.0.0.5"] if host == "internal.example.org" else ["93.184.216.34"]

    with pytest.raises(StockError) as caught:
        await download_public("https://cdn.example.org/a.mp3", resolver=resolver, client=_recording_client(handler))

    assert caught.value.code == "stock_download_rejected"
    assert seen == ["cdn.example.org"]


async def test_a_redirect_is_followed_to_another_public_host_and_loops_are_cut_off() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.headers["Host"] == "cdn.example.org":
            return httpx2.Response(301, headers={"Location": "https://files.example.org/b.mp3"})
        return httpx2.Response(200, content=b"MOVED")

    def loop(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(302, headers={"Location": "https://cdn.example.org/again"})

    async def resolver(_host: str, _port: int) -> Iterable[str]:
        return ["93.184.216.34"]

    moved = await download_public("https://cdn.example.org/a.mp3", resolver=resolver, client=_recording_client(handler))
    assert moved == b"MOVED"
    with pytest.raises(StockError) as caught:
        await download_public("https://cdn.example.org/a.mp3", resolver=resolver, client=_recording_client(loop))
    assert caught.value.code == "stock_download_rejected"


async def test_a_download_stops_at_the_size_limit() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"x", headers={"Content-Length": str(STOCK_FILE_MAX_BYTES + 1)})

    with pytest.raises(ArtifactTooLargeError):
        await download_public("https://93.184.216.34/big.wav", client=_recording_client(handler))


@pytest.mark.parametrize(
    ("title", "extension", "expected"),
    [
        ("door_slam.wav", ".mp3", "door_slam.mp3"),
        ("rain / on a roof v1.2", ".wav", "rain   on a roof v1.2.wav"),
        ("Chopin", ".mp3", "Chopin.mp3"),
        (".ogg", ".mp3", ".ogg.mp3"),
    ],
)
def test_the_file_name_drops_a_duplicate_audio_extension(title: str, extension: str, expected: str) -> None:
    assert stock_file_name(title, extension) == expected
