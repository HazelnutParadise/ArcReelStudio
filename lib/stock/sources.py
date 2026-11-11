"""四个素材来源：Openverse、Pixabay、Pexels、Freesound。

每个来源只做两件事：按关键字搜索、按 id 重取一条。授权过滤写在请求参数里，并在解析响应时再核对一次，
来源返回了范围之外的授权就丢掉那一条。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import urlsplit

import httpx2

from lib.stock.model import (
    KeyScope,
    ResolvedStockItem,
    StockError,
    StockItem,
    StockKind,
    StockLicense,
    StockSource,
)

PAGE_SIZE = 20

_AUDIO_EXTENSIONS = (".mp3", ".wav", ".m4a")
_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def _extension(url: str, allowed: tuple[str, ...]) -> str | None:
    path = urlsplit(url).path.lower()
    return next((extension for extension in allowed if path.endswith(extension)), None)


def _text(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


async def _get_json(
    client: httpx2.AsyncClient,
    source: str,
    url: str,
    *,
    params: Mapping[str, str | int] | None = None,
    headers: Mapping[str, str] | None = None,
) -> Any:
    try:
        response = await client.get(url, params=params, headers=headers)
    except httpx2.HTTPError as exc:
        raise StockError("stock_source_failed", f"{source} 请求失败：{exc}", source=source) from exc
    if response.status_code in (401, 403):
        raise StockError("stock_key_rejected", f"{source} 拒绝了密钥", source=source)
    if response.status_code == 404:
        raise StockError("stock_item_not_found", f"{source} 没有这条素材", source=source)
    if response.status_code >= 400:
        raise StockError("stock_source_failed", f"{source} 返回 {response.status_code}", source=source)
    try:
        return response.json()
    except ValueError as exc:
        raise StockError("stock_source_failed", f"{source} 返回的不是 JSON", source=source) from exc


def _require_key(source: str, key: str | None) -> str:
    if not key:
        raise StockError("stock_key_missing", f"{source} 需要密钥", source=source)
    return key


def _unsupported(source: str, kind: StockKind) -> StockError:
    return StockError("stock_kind_unsupported", f"{source} 不提供 {kind}", source=source, kind=kind)


def _rows(payload: object, field: str) -> list[Mapping[str, Any]]:
    rows = payload.get(field) if isinstance(payload, Mapping) else None
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


class OpenverseSource:
    """Openverse：CC0 与公有领域的图片、音乐、音效。不需要密钥（匿名额度每分钟 20 次）。

    音频不取 Freesound 来的条目：那些档案受 Freesound 条款约束，要用成员自己的 Freesound 密钥经 Freesound 来源取。
    """

    id = "openverse"
    display_name = "Openverse"
    kinds: frozenset[StockKind] = frozenset({"music", "sfx", "image"})
    key_scope: KeyScope = "none"
    key_url: str | None = None

    _BASE = "https://api.openverse.org/v1"
    _CATEGORY: Mapping[str, str] = {"music": "music", "sfx": "sound_effect"}

    def _endpoint(self, kind: StockKind) -> str:
        return f"{self._BASE}/{'images' if kind == 'image' else 'audio'}/"

    def _item(self, kind: StockKind, row: Mapping[str, Any]) -> ResolvedStockItem | None:
        item_id, url, license_code = _text(row.get("id")), _text(row.get("url")), _text(row.get("license"))
        if item_id is None or url is None or license_code not in ("cc0", "pdm"):
            return None
        if kind != "image" and row.get("source") == "freesound":
            return None
        extension = _extension(url, _IMAGE_EXTENSIONS if kind == "image" else _AUDIO_EXTENSIONS)
        if extension is None:
            return None
        duration_ms = _number(row.get("duration"))
        item = StockItem(
            source=self.id,
            id=item_id,
            kind=kind,
            title=_text(row.get("title")) or item_id,
            creator=_text(row.get("creator")),
            license=cast(StockLicense, license_code),
            license_url=_text(row.get("license_url")) or "https://creativecommons.org/publicdomain/zero/1.0/",
            page_url=_text(row.get("foreign_landing_url")) or url,
            preview_url=_text(row.get("thumbnail")) if kind == "image" else url,
            duration_seconds=round(duration_ms / 1000, 3) if duration_ms else None,
            width=_integer(row.get("width")),
            height=_integer(row.get("height")),
        )
        return ResolvedStockItem(item=item, download_url=url, extension=extension)

    async def search(
        self, client: httpx2.AsyncClient, *, kind: StockKind, query: str, page: int, key: str | None
    ) -> list[StockItem]:
        params: dict[str, str | int] = {"q": query, "license": "cc0,pdm", "page": page, "page_size": PAGE_SIZE}
        if kind == "image":
            params["extension"] = "jpg,jpeg,png,webp"
        else:
            params.update(category=self._CATEGORY[kind], extension="mp3,wav,m4a", excluded_source="freesound")
        payload = await _get_json(client, self.id, self._endpoint(kind), params=params)
        resolved = (self._item(kind, row) for row in _rows(payload, "results"))
        return [entry.item for entry in resolved if entry is not None]

    async def resolve(
        self, client: httpx2.AsyncClient, *, kind: StockKind, item_id: str, key: str | None
    ) -> ResolvedStockItem:
        payload = await _get_json(client, self.id, f"{self._endpoint(kind)}{item_id}/")
        resolved = self._item(kind, payload) if isinstance(payload, Mapping) else None
        if resolved is None:
            raise StockError("stock_item_not_found", "Openverse 没有这条可用的素材", source=self.id)
        return resolved


class PixabaySource:
    """Pixabay：图片。授权免署名可商用；条款要求把档案下载到自己的服务器，不长期热链。"""

    id = "pixabay"
    display_name = "Pixabay"
    kinds: frozenset[StockKind] = frozenset({"image"})
    key_scope: KeyScope = "workspace"
    key_url: str | None = "https://pixabay.com/api/docs/"

    _URL = "https://pixabay.com/api/"
    _LICENSE_URL = "https://pixabay.com/service/license-summary/"

    def _item(self, row: Mapping[str, Any]) -> ResolvedStockItem | None:
        item_id, url = _integer(row.get("id")), _text(row.get("largeImageURL")) or _text(row.get("webformatURL"))
        if item_id is None or url is None:
            return None
        extension = _extension(url, _IMAGE_EXTENSIONS)
        if extension is None:
            return None
        item = StockItem(
            source=self.id,
            id=str(item_id),
            kind="image",
            title=_text(row.get("tags")) or str(item_id),
            creator=_text(row.get("user")),
            license="pixabay",
            license_url=self._LICENSE_URL,
            page_url=_text(row.get("pageURL")) or "https://pixabay.com/",
            preview_url=_text(row.get("webformatURL")) or _text(row.get("previewURL")),
            width=_integer(row.get("imageWidth")),
            height=_integer(row.get("imageHeight")),
        )
        return ResolvedStockItem(item=item, download_url=url, extension=extension)

    async def _hits(self, client: httpx2.AsyncClient, params: dict[str, str | int]) -> list[ResolvedStockItem]:
        payload = await _get_json(client, self.id, self._URL, params=params)
        resolved = (self._item(row) for row in _rows(payload, "hits"))
        return [entry for entry in resolved if entry is not None]

    async def search(
        self, client: httpx2.AsyncClient, *, kind: StockKind, query: str, page: int, key: str | None
    ) -> list[StockItem]:
        if kind != "image":
            raise _unsupported(self.id, kind)
        params: dict[str, str | int] = {
            "key": _require_key(self.id, key),
            "q": query,
            "image_type": "photo",
            "safesearch": "true",
            "page": page,
            "per_page": PAGE_SIZE,
        }
        return [entry.item for entry in await self._hits(client, params)]

    async def resolve(
        self, client: httpx2.AsyncClient, *, kind: StockKind, item_id: str, key: str | None
    ) -> ResolvedStockItem:
        if kind != "image":
            raise _unsupported(self.id, kind)
        hits = await self._hits(client, {"key": _require_key(self.id, key), "id": item_id})
        if not hits:
            raise StockError("stock_item_not_found", "Pixabay 没有这张图片", source=self.id)
        return hits[0]


class PexelsSource:
    """Pexels：图片。授权免署名可商用。"""

    id = "pexels"
    display_name = "Pexels"
    kinds: frozenset[StockKind] = frozenset({"image"})
    key_scope: KeyScope = "workspace"
    key_url: str | None = "https://www.pexels.com/api/"

    _BASE = "https://api.pexels.com/v1"
    _LICENSE_URL = "https://www.pexels.com/license/"

    def _item(self, row: Mapping[str, Any]) -> ResolvedStockItem | None:
        item_id = _integer(row.get("id"))
        sizes = row.get("src")
        if item_id is None or not isinstance(sizes, Mapping):
            return None
        url = _text(sizes.get("large2x")) or _text(sizes.get("large")) or _text(sizes.get("original"))
        if url is None:
            return None
        item = StockItem(
            source=self.id,
            id=str(item_id),
            kind="image",
            title=_text(row.get("alt")) or str(item_id),
            creator=_text(row.get("photographer")),
            license="pexels",
            license_url=self._LICENSE_URL,
            page_url=_text(row.get("url")) or "https://www.pexels.com/",
            preview_url=_text(sizes.get("medium")) or _text(sizes.get("tiny")),
            width=_integer(row.get("width")),
            height=_integer(row.get("height")),
        )
        # Pexels 的尺寸变体地址带查询参数，扩展名看路径；看不出时按它统一提供的 JPEG 处理。
        return ResolvedStockItem(item=item, download_url=url, extension=_extension(url, _IMAGE_EXTENSIONS) or ".jpg")

    async def search(
        self, client: httpx2.AsyncClient, *, kind: StockKind, query: str, page: int, key: str | None
    ) -> list[StockItem]:
        if kind != "image":
            raise _unsupported(self.id, kind)
        payload = await _get_json(
            client,
            self.id,
            f"{self._BASE}/search",
            params={"query": query, "page": page, "per_page": PAGE_SIZE},
            headers={"Authorization": _require_key(self.id, key)},
        )
        resolved = (self._item(row) for row in _rows(payload, "photos"))
        return [entry.item for entry in resolved if entry is not None]

    async def resolve(
        self, client: httpx2.AsyncClient, *, kind: StockKind, item_id: str, key: str | None
    ) -> ResolvedStockItem:
        if kind != "image":
            raise _unsupported(self.id, kind)
        payload = await _get_json(
            client, self.id, f"{self._BASE}/photos/{item_id}", headers={"Authorization": _require_key(self.id, key)}
        )
        resolved = self._item(payload) if isinstance(payload, Mapping) else None
        if resolved is None:
            raise StockError("stock_item_not_found", "Pexels 没有这张图片", source=self.id)
        return resolved


class FreesoundSource:
    """Freesound：真实录音的音效，只取 CC0。每位成员用自己的 Freesound 密钥；取的是高音质试听档（MP3）。

    Freesound 的条款不允许把它的内容转供给没有 Freesound 账号的人，所以密钥按成员存，不设工作区共用的一把。
    """

    id = "freesound"
    display_name = "Freesound"
    kinds: frozenset[StockKind] = frozenset({"sfx"})
    key_scope: KeyScope = "member"
    key_url: str | None = "https://freesound.org/apiv2/apply"

    _BASE = "https://freesound.org/apiv2"
    _FIELDS = "id,name,username,license,url,duration,previews"
    _CC0_MARKERS = ("creative commons 0", "publicdomain/zero")

    def _item(self, row: Mapping[str, Any]) -> ResolvedStockItem | None:
        item_id, license_text = _integer(row.get("id")), (_text(row.get("license")) or "").lower()
        previews = row.get("previews")
        if item_id is None or not isinstance(previews, Mapping):
            return None
        if not any(marker in license_text for marker in self._CC0_MARKERS):
            return None
        url = _text(previews.get("preview-hq-mp3"))
        if url is None:
            return None
        item = StockItem(
            source=self.id,
            id=str(item_id),
            kind="sfx",
            title=_text(row.get("name")) or str(item_id),
            creator=_text(row.get("username")),
            license="cc0",
            license_url="https://creativecommons.org/publicdomain/zero/1.0/",
            page_url=_text(row.get("url")) or "https://freesound.org/",
            preview_url=url,
            duration_seconds=_number(row.get("duration")),
        )
        return ResolvedStockItem(item=item, download_url=url, extension=".mp3")

    def _headers(self, key: str | None) -> dict[str, str]:
        return {"Authorization": f"Token {_require_key(self.id, key)}"}

    async def search(
        self, client: httpx2.AsyncClient, *, kind: StockKind, query: str, page: int, key: str | None
    ) -> list[StockItem]:
        if kind != "sfx":
            raise _unsupported(self.id, kind)
        payload = await _get_json(
            client,
            self.id,
            f"{self._BASE}/search/text/",
            params={
                "query": query,
                "filter": 'license:"Creative Commons 0"',
                "fields": self._FIELDS,
                "page": page,
                "page_size": PAGE_SIZE,
            },
            headers=self._headers(key),
        )
        resolved = (self._item(row) for row in _rows(payload, "results"))
        return [entry.item for entry in resolved if entry is not None]

    async def resolve(
        self, client: httpx2.AsyncClient, *, kind: StockKind, item_id: str, key: str | None
    ) -> ResolvedStockItem:
        if kind != "sfx":
            raise _unsupported(self.id, kind)
        payload = await _get_json(
            client,
            self.id,
            f"{self._BASE}/sounds/{item_id}/",
            params={"fields": self._FIELDS},
            headers=self._headers(key),
        )
        resolved = self._item(payload) if isinstance(payload, Mapping) else None
        if resolved is None:
            raise StockError("stock_item_not_found", "Freesound 没有这条可用的音效", source=self.id)
        return resolved


STOCK_SOURCES: Mapping[str, StockSource] = {
    source.id: source for source in (OpenverseSource(), PixabaySource(), PexelsSource(), FreesoundSource())
}
