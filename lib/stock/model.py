"""免版权素材库的共用形状：素材条目、来源声明与错误（docs/adr/0128）。

只收「不用署名就能商用」的素材：CC0、公有领域，以及 Pixabay / Pexels 自己的授权。要求署名（CC BY 等）或
禁止商用的素材在来源一侧就过滤掉，这里的 :data:`StockLicense` 没有它们的位置。
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

import httpx2
from pydantic import BaseModel, ConfigDict

#: 素材用途：BGM、音效、图片。
StockKind = Literal["music", "sfx", "image"]
STOCK_KINDS: tuple[StockKind, ...] = ("music", "sfx", "image")

#: 允许出现的授权。``cc0`` / ``pdm`` 是 Creative Commons 的公有领域贡献与公有领域标记。
StockLicense = Literal["cc0", "pdm", "pixabay", "pexels"]

#: 来源的密钥归谁：不需要、整个工作区共用一把（管理员设置）、每位成员用自己的。
KeyScope = Literal["none", "workspace", "member"]

StockErrorCode = Literal[
    "stock_unknown_source",
    "stock_kind_unsupported",
    "stock_key_missing",
    "stock_key_rejected",
    "stock_item_not_found",
    "stock_source_failed",
    "stock_download_rejected",
    "stock_file_too_large",
    "stock_file_unsupported",
]


class StockError(Exception):
    """素材库的预期内失败；``code`` 同时是错误文案的键。"""

    def __init__(self, code: StockErrorCode, message: str, **params: Any) -> None:
        super().__init__(message)
        self.code: StockErrorCode = code
        self.params = params


class StockItem(BaseModel):
    """一条搜索结果。``preview_url`` 是缩略图（图片）或试听档（音频）；下载地址不放进来，导入时按 id 向来源重取。"""

    model_config = ConfigDict(frozen=True)

    source: str
    id: str
    kind: StockKind
    title: str
    creator: str | None = None
    license: StockLicense
    license_url: str
    page_url: str
    preview_url: str | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None


class ResolvedStockItem(BaseModel):
    """按 id 向来源重取的一条素材，带服务端下载用的地址与文件扩展名。"""

    model_config = ConfigDict(frozen=True)

    item: StockItem
    download_url: str
    extension: str


class StockSource(Protocol):
    """一个素材来源。``search`` 与 ``resolve`` 只返回 :data:`StockLicense` 之内的素材。"""

    id: str
    display_name: str
    kinds: frozenset[StockKind]
    key_scope: KeyScope
    #: 取得密钥的页面，没有密钥的来源为 None。
    key_url: str | None

    async def search(
        self, client: httpx2.AsyncClient, *, kind: StockKind, query: str, page: int, key: str | None
    ) -> list[StockItem]: ...

    async def resolve(
        self, client: httpx2.AsyncClient, *, kind: StockKind, item_id: str, key: str | None
    ) -> ResolvedStockItem: ...
