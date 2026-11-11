"""Host-neutral stock library tools: search attribution-free music and sound effects, and import one into the project.

Only the workspace-shared source keys are used here. Sources whose key belongs to a member (Freesound) are not
available to the Agent: the Agent does not act as a particular member.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lib.bgm.service import BgmError, BgmLibraryService
from lib.db.models.stock_source_key import WORKSPACE_OWNER
from lib.sfx.service import SfxError, SfxLibraryService
from lib.stock.model import StockError, StockItem
from lib.stock.service import StockLibraryService
from server.media_tools.context import tool_error, tool_problem
from server.services.stock_access import stock_keys
from server.tool_runtime import CallerContext, ProjectScope, Services, ToolOutcome, ToolRequest

StockAudioKind = Literal["music", "sfx"]


class SearchStockAudioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: StockAudioKind = Field(description="music 找 BGM，sfx 找音效")
    query: str = Field(min_length=1, max_length=200, description="搜索词，英文结果最多，例如 calm piano、door slam")
    page: int = Field(default=1, ge=1, le=50, description="第几页，每个来源每页最多 20 条")


class StockAudioItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    id: str
    title: str
    duration: float | None
    license: str


class StockAudioSearch(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[StockAudioItem, ...]
    #: 没有返回结果的来源与原因：key_missing、key_rejected、failed
    unavailable: dict[str, str]


def _audio_item(item: StockItem) -> StockAudioItem:
    return StockAudioItem(
        source=item.source, id=item.id, title=item.title, duration=item.duration_seconds, license=item.license
    )


async def _workspace_keys(services: Services, library: StockLibraryService) -> dict[str, str]:
    async with services.sessions() as session:
        return await stock_keys(session, library, WORKSPACE_OWNER)


async def search_stock_audio(
    request: ToolRequest[SearchStockAudioRequest],
    _scope: ProjectScope,
    _caller: CallerContext,
    services: Services,
) -> ToolOutcome[StockAudioSearch]:
    args = request.value
    library = StockLibraryService()
    try:
        keys = await _workspace_keys(services, library)
        result = await library.search(kind=args.kind, query=args.query.strip(), page=args.page, keys=keys)
    except Exception as exc:
        return tool_error("search_stock_audio", exc)
    return ToolOutcome(
        value=StockAudioSearch(
            items=tuple(_audio_item(item) for item in result.items),
            unavailable={entry.source: entry.status for entry in result.sources if entry.status != "ok"},
        )
    )


def stock_audio_search_summary(value: StockAudioSearch) -> str:
    lines = [
        f"- {item.source} {item.id}「{item.title}」"
        + (f"{item.duration} 秒" if item.duration is not None else "长度未知")
        + f"（{item.license}）"
        for item in value.items
    ]
    if value.unavailable:
        lines.append("没有结果的来源：" + "、".join(f"{source}（{why}）" for source, why in value.unavailable.items()))
    return "\n".join(lines) or "没有找到素材；换一个搜索词，或改用生成"


class ImportStockAudioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: StockAudioKind = Field(description="music 存进 BGM 库，sfx 存进音效库")
    source: str = Field(min_length=1, max_length=32, description="search_stock_audio 结果里的 source")
    id: str = Field(min_length=1, max_length=128, description="search_stock_audio 结果里的 id")


class ImportedStockAudio(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: StockAudioKind
    #: BGM 库或音效库里的 id，edit_timeline 的 insert_bgm / insert_sfx 用它引用
    id: str
    name: str
    duration: float


async def import_stock_audio(
    request: ToolRequest[ImportStockAudioRequest],
    scope: ProjectScope,
    _caller: CallerContext,
    services: Services,
) -> ToolOutcome[ImportedStockAudio]:
    args = request.value
    library = StockLibraryService()
    try:
        keys = await _workspace_keys(services, library)
        file = await library.fetch(source_id=args.source, kind=args.kind, item_id=args.id, key=keys.get(args.source))
        name = f"{file.item.title.replace('/', ' ').replace(chr(92), ' ')}{file.extension}"
        if args.kind == "music":
            track = await BgmLibraryService(services.projects).register_library(
                scope.project_name,
                name=name,
                extension=file.extension,
                content=file.content,
                license=file.item.license,
                source_url=file.item.page_url,
            )
            return ToolOutcome(
                value=ImportedStockAudio(kind="music", id=track.id, name=track.name, duration=track.duration)
            )
        sound = await SfxLibraryService(services.projects).register_library(
            scope.project_name,
            name=name,
            extension=file.extension,
            content=file.content,
            license=file.item.license,
            source_url=file.item.page_url,
        )
    except (StockError, BgmError, SfxError) as exc:
        return tool_problem(str(exc), code=exc.code, params=exc.params or None)
    except Exception as exc:
        return tool_error("import_stock_audio", exc)
    return ToolOutcome(value=ImportedStockAudio(kind="sfx", id=sound.id, name=sound.name, duration=sound.duration))


def imported_stock_audio_summary(value: ImportedStockAudio) -> str:
    operation = "insert_bgm" if value.kind == "music" else "insert_sfx"
    return f"已导入 {value.id}「{value.name}」{value.duration} 秒，可用 edit_timeline 的 {operation} 摆放"


__all__ = [
    "ImportStockAudioRequest",
    "ImportedStockAudio",
    "SearchStockAudioRequest",
    "StockAudioSearch",
    "import_stock_audio",
    "imported_stock_audio_summary",
    "search_stock_audio",
    "stock_audio_search_summary",
]
