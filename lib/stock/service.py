"""免版权素材库的搜索与下载。

搜索同时问所有提供这种素材的来源，一个来源失败不影响其他来源，各来源的状态一并返回。下载地址不信任前端：
导入时按 ``(来源, id)`` 向来源重取，再从它给的地址下载，下载只走 HTTPS、目标必须是公网地址，并直接连到校验过的地址。
"""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Awaitable, Callable, Mapping
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


#: 不算公网、但 ``is_global`` 会放行的地址段：NAT64 与 IPv4 兼容地址能把内网的 IPv4 地址包在 IPv6 里。
_EMBEDDED_IPV4_NETWORKS = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("::/96"))

#: 下载器：给地址，返回档案字节。测试换成不做公网校验的版本。
Downloader = Callable[[str], Awaitable[bytes]]

_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def _is_public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif any(ip in network for network in _EMBEDDED_IPV4_NETWORKS):
            return False
    return ip.is_global


async def public_addresses(url: httpx2.URL, *, resolver: Resolver = resolve_host) -> list[str]:
    """``url`` 的主机解析出的地址。素材档案只从公网 HTTPS 地址下载：协议不是 HTTPS、解析不了主机，
    或任一地址落在内网、环回、云元数据地址上，都抛 ``stock_download_rejected``。"""
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
    if not addresses or not all(_is_public_address(address) for address in addresses):
        raise StockError("stock_download_rejected", f"素材主机不是公网地址：{host}")
    return addresses


async def check_public_destination(url: httpx2.URL, *, resolver: Resolver = resolve_host) -> None:
    """校验 ``url`` 是公网 HTTPS 地址，见 :func:`public_addresses`。"""
    await public_addresses(url, resolver=resolver)


async def download_public(
    url: str,
    *,
    resolver: Resolver = resolve_host,
    client: Callable[[], httpx2.AsyncClient] | None = None,
) -> bytes:
    """从公网 HTTPS 地址下载一个档案，最多跟随三跳重定向，超过 :data:`STOCK_FILE_MAX_BYTES` 即中止。

    每一跳都先解析并校验主机，再直接连到校验过的那个地址（以原主机名做 TLS 的 SNI 与证书校验，``Host`` 头
    照旧）。连接不再另做一次解析，所以主机名在校验之后改指内网地址也连不过去。
    """
    make_client = client or (lambda: httpx2.AsyncClient(timeout=_DOWNLOAD_TIMEOUT_SECONDS, headers=_HEADERS))
    current = httpx2.URL(url)
    async with make_client() as http:
        for _ in range(_MAX_REDIRECTS + 1):
            address = (await public_addresses(current, resolver=resolver))[0]
            pinned = current.copy_with(host=address)
            request = http.build_request(
                "GET",
                pinned,
                headers={"Host": current.netloc.decode("ascii")},
                extensions={"sni_hostname": current.host},
            )
            response = await http.send(request, stream=True)
            try:
                if response.status_code in _REDIRECT_STATUSES and "location" in response.headers:
                    current = current.join(response.headers["location"])
                    continue
                if response.status_code >= 400:
                    raise StockError("stock_source_failed", f"素材下载返回 {response.status_code}", source=current.host)
                return await read_body_capped(response, max_bytes=STOCK_FILE_MAX_BYTES)
            finally:
                await response.aclose()
    raise StockError("stock_download_rejected", "素材地址的重定向次数过多")


_NAME_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg", ".oga", ".flac")


def stock_file_name(title: str, extension: str) -> str:
    """登记进 BGM 库或音效库时用的文件名：库从文件名去掉扩展名取显示名。

    标题里的路径分隔符换成空格，免得只剩最后一段；标题本身已带音频扩展名（Freesound 的名字常是原文件名）
    时先去掉，免得显示名多出一截扩展名。
    """
    name = title.replace("/", " ").replace("\\", " ").strip()
    lowered = name.lower()
    for known in _NAME_EXTENSIONS:
        if lowered.endswith(known) and len(name) > len(known):
            name = name[: -len(known)]
            break
    return f"{name}{extension}"


class StockLibraryService:
    """``api_client`` 与 ``download`` 可注入，测试用它们接上假的来源。"""

    def __init__(
        self,
        *,
        sources: Mapping[str, StockSource] = STOCK_SOURCES,
        api_client: Callable[[], httpx2.AsyncClient] | None = None,
        download: Downloader | None = None,
    ) -> None:
        self._sources = sources
        self._api_client = api_client or (lambda: httpx2.AsyncClient(timeout=_API_TIMEOUT_SECONDS, headers=_HEADERS))
        self._download = download or download_public

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
        try:
            content = await self._download(resolved.download_url)
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
