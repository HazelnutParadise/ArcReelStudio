"""免版权素材库的搜索与下载。

搜索同时问所有提供这种素材的来源，一个来源失败不影响其他来源，各来源的状态一并返回。下载地址不信任前端：
导入时按 ``(来源, id)`` 向来源重取，再从它给的地址下载，下载只走 HTTPS 且目标必须是公网地址。
"""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Callable, Mapping
from itertools import chain, zip_longest
from typing import Literal

import httpx2
from pydantic import BaseModel, ConfigDict

from lib.backends.artifact_download_guard import (
    DNS_RESOLVE_TIMEOUT_SECONDS,
    ArtifactTooLargeError,
    Resolver,
    read_body_capped,
    resolve_host,
)
from lib.stock.model import ResolvedStockItem, StockError, StockItem, StockKind, StockSource
from lib.stock.sources import STOCK_SOURCES
from lib.stock.transcode import to_storable_audio

#: 单个素材档案的上限：音频与 BGM 库的上限一致，图片远小于此。
STOCK_FILE_MAX_BYTES = 100 * 1024 * 1024

#: 素材来源（尤其维基共享资源）会拒绝没有标明身份的请求：带上应用名与项目主页。
_HEADERS = {"User-Agent": "ArcReelStudio (+https://github.com/HazelnutParadise/ArcReelStudio)"}

_API_TIMEOUT_SECONDS = 15.0
_DOWNLOAD_TIMEOUT_SECONDS = 120.0

SourceStatus = Literal["ok", "key_missing", "key_rejected", "failed"]

_STATUS_BY_CODE: Mapping[str, SourceStatus] = {
    "stock_key_missing": "key_missing",
    "stock_key_rejected": "key_rejected",
}


class SourceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    status: SourceStatus


class StockSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[StockItem, ...]
    sources: tuple[SourceResult, ...]


class StockFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: StockItem
    extension: str
    content: bytes


async def check_public_destination(url: httpx2.URL, *, resolver: Resolver = resolve_host) -> None:
    """素材档案只从公网 HTTPS 地址下载；内网、环回与云元数据地址一律拒绝。解析不了主机也拒绝。"""
    if url.scheme != "https":
        raise StockError("stock_download_rejected", f"素材地址不是 HTTPS：{url.scheme or '(无)'}")
    host = url.host
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            async with asyncio.timeout(DNS_RESOLVE_TIMEOUT_SECONDS):
                addresses = list(await resolver(host, url.port or 443))
        except OSError as exc:  # TimeoutError 亦是 OSError
            raise StockError("stock_download_rejected", f"素材主机解析失败：{host}") from exc
    if not addresses or not all(ipaddress.ip_address(address).is_global for address in addresses):
        raise StockError("stock_download_rejected", f"素材主机不是公网地址：{host}")


def _download_client(resolver: Resolver) -> httpx2.AsyncClient:
    async def guard(request: httpx2.Request) -> None:
        await check_public_destination(request.url, resolver=resolver)

    return httpx2.AsyncClient(
        event_hooks={"request": [guard]},
        follow_redirects=True,
        max_redirects=3,
        timeout=_DOWNLOAD_TIMEOUT_SECONDS,
        headers=_HEADERS,
    )


class StockLibraryService:
    """``api_client`` 与 ``download_client`` 可注入，测试用它们接上假的来源。"""

    def __init__(
        self,
        *,
        sources: Mapping[str, StockSource] = STOCK_SOURCES,
        api_client: Callable[[], httpx2.AsyncClient] | None = None,
        download_client: Callable[[], httpx2.AsyncClient] | None = None,
    ) -> None:
        self._sources = sources
        self._api_client = api_client or (lambda: httpx2.AsyncClient(timeout=_API_TIMEOUT_SECONDS, headers=_HEADERS))
        self._download_client = download_client or (lambda: _download_client(resolve_host))

    def sources(self) -> tuple[StockSource, ...]:
        return tuple(self._sources.values())

    def source(self, source_id: str) -> StockSource:
        try:
            return self._sources[source_id]
        except KeyError:
            raise StockError("stock_unknown_source", f"没有这个素材来源：{source_id}", source=source_id) from None

    async def search(
        self, *, kind: StockKind, query: str, page: int, keys: Mapping[str, str | None]
    ) -> StockSearchResult:
        """问所有提供 ``kind`` 的来源，结果按来源轮流排列。``keys`` 是来源 id 到当前成员可用密钥的映射。"""
        sources = [source for source in self._sources.values() if kind in source.kinds]

        async def one(client: httpx2.AsyncClient, source: StockSource) -> tuple[list[StockItem], SourceStatus]:
            if source.key_scope != "none" and not keys.get(source.id):
                return [], "key_missing"
            try:
                return await source.search(client, kind=kind, query=query, page=page, key=keys.get(source.id)), "ok"
            except StockError as exc:
                return [], _STATUS_BY_CODE.get(exc.code, "failed")

        async with self._api_client() as client:
            outcomes = await asyncio.gather(*(one(client, source) for source in sources))
        interleaved = chain.from_iterable(zip_longest(*(items for items, _ in outcomes)))
        return StockSearchResult(
            items=tuple(item for item in interleaved if item is not None),
            sources=tuple(
                SourceResult(source=source.id, status=status)
                for source, (_, status) in zip(sources, outcomes, strict=True)
            ),
        )

    async def resolve(self, *, source_id: str, kind: StockKind, item_id: str, key: str | None) -> ResolvedStockItem:
        source = self.source(source_id)
        if kind not in source.kinds:
            raise StockError("stock_kind_unsupported", f"{source_id} 不提供 {kind}", source=source_id, kind=kind)
        if source.key_scope != "none" and not key:
            raise StockError("stock_key_missing", f"{source_id} 需要密钥", source=source.display_name)
        async with self._api_client() as client:
            return await source.resolve(client, kind=kind, item_id=item_id, key=key)

    async def fetch(self, *, source_id: str, kind: StockKind, item_id: str, key: str | None) -> StockFile:
        """按 id 向来源重取这条素材并下载档案。音频若是库里不收的格式（OGG、FLAC），转成 MP3 再返回。"""
        resolved = await self.resolve(source_id=source_id, kind=kind, item_id=item_id, key=key)
        async with self._download_client() as client:
            try:
                async with client.stream("GET", resolved.download_url) as response:
                    if response.status_code >= 400:
                        raise StockError(
                            "stock_source_failed", f"素材下载返回 {response.status_code}", source=source_id
                        )
                    content = await read_body_capped(response, max_bytes=STOCK_FILE_MAX_BYTES)
            except ArtifactTooLargeError as exc:
                raise StockError(
                    "stock_file_too_large", "素材档案过大", max_mb=STOCK_FILE_MAX_BYTES // (1024 * 1024)
                ) from exc
            except httpx2.HTTPError as exc:
                raise StockError("stock_source_failed", f"素材下载失败：{exc}", source=source_id) from exc
        extension = resolved.extension
        if kind != "image":
            content, extension = await to_storable_audio(content, extension)
        return StockFile(item=resolved.item, extension=extension, content=content)
