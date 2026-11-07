"""可以多人同时编辑的「编辑单元」：每种单元怎么从项目文件读出、改了之后怎么写回。

一个单元对应界面上的一个编辑区（项目概述、某个角色、某一格分镜……）。协作文档的内容就是 :meth:`UnitSpec.read`
返回的对象（存储里的字段，按白名单挑出），写回时只交出改动过的顶层字段，走与 REST 接口同一套修改逻辑。

读写都是同步的文件操作，由调用方放进线程执行。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeIs

from pydantic import ValidationError

from lib.agent.agent_memory_store import AgentMemoryStore
from lib.db.base import DEFAULT_USER_ID
from lib.db.repositories.asset_repo import AssetRepository
from lib.episode.episode_ledger import parse_positive_episode_num
from lib.episode.episode_paths import episode_source_path
from lib.episode.episode_source_commands import EpisodeSourceError, set_episode_source_text
from lib.infra.api_errors import ApiError, NotFoundError
from lib.infra.async_thread import run_sync_transaction
from lib.project.asset_derivatives import derivative_table, ensure_derivative_table
from lib.project.asset_types import ASSET_SPECS, asset_name_comparison_key, resolve_asset_key
from lib.project.project_manager import ProjectManager
from lib.script.script_batch_edit import ScriptBatchEditCommand, ScriptBatchEditor, script_revision
from server.services.asset_library_fields import LIBRARY_ASSET_TEXT_FIELDS, update_library_asset_fields
from server.services.project.project_settings_patch import ProjectSettingsPatch, apply_project_settings_patch


class UnitNotFoundError(LookupError):
    """单元已不存在（项目、角色或分镜被删除或改名）。"""


class UnitWriteError(ValueError):
    """内容不合规，不能写回；``code`` 是给界面本地化用的稳定键（可以直接是错误文案的 i18n key）。"""

    def __init__(self, code: str, detail: str = "", params: dict[str, object] | None = None) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail
        #: 渲染错误文案的参数（如区间上下限）
        self.params = params or {}


@dataclass(frozen=True)
class UnitRef:
    project: str
    kind: str
    key: str


class UnitSpec(Protocol):
    """项目里的单元：读写是同步的文件操作，由中枢放进线程执行；外部改动来自项目事件流。"""

    kind: str

    def read(self, pm: ProjectManager, project: str, key: str) -> dict[str, Any]:
        """单元当前的内容；不存在时抛 :class:`UnitNotFoundError`。"""
        ...

    def write(self, pm: ProjectManager, project: str, key: str, changes: dict[str, Any]) -> None:
        """写回改动过的顶层字段；内容不合规时抛 :class:`UnitWriteError`。"""
        ...


class GlobalUnitSpec(Protocol):
    """不属于项目的单元（全局资产库、工作区记忆等）：房间的 ``project`` 为空串，读写是协程。

    没有项目事件流可订阅，中枢在房间打开期间定时重读，别处（接口、Agent）的改动照样并进文档。
    """

    kind: str
    scope: Literal["global"]

    async def read(self, key: str) -> dict[str, Any]:
        """单元当前的内容；不存在时抛 :class:`UnitNotFoundError`。"""
        ...

    async def write(self, key: str, changes: dict[str, Any]) -> None:
        """写回改动过的顶层字段；内容不合规时抛 :class:`UnitWriteError`。"""
        ...


AnyUnitSpec = UnitSpec | GlobalUnitSpec


def is_global(spec: AnyUnitSpec) -> TypeIs[GlobalUnitSpec]:
    return getattr(spec, "scope", "project") == "global"


# ── 项目概述 ─────────────────────────────────────────────────────

_OVERVIEW_FIELDS = ("synopsis", "genre", "theme", "world_setting")


class OverviewUnit:
    kind = "overview"

    def read(self, pm: ProjectManager, project: str, key: str) -> dict[str, Any]:
        raw = _load_project(pm, project).get("overview")
        overview: dict[str, Any] = raw if isinstance(raw, dict) else {}
        return {field: _text(overview.get(field)) for field in _OVERVIEW_FIELDS}

    def write(self, pm: ProjectManager, project: str, key: str, changes: dict[str, Any]) -> None:
        updates = {f: _text(changes[f]).strip() for f in _OVERVIEW_FIELDS if f in changes}
        if not updates:
            return

        def _mutate(data: dict) -> None:
            if not isinstance(data.get("overview"), dict):
                data["overview"] = {}
            data["overview"].update(updates)

        try:
            pm.update_project(project, _mutate)
        except FileNotFoundError as exc:
            raise UnitNotFoundError(project) from exc


# ── 广告创意简报 ─────────────────────────────────────────────────


class BriefUnit:
    """广告项目的创意灵感与目标总时长（``project.json`` 的 ``brief`` / ``target_duration``）。"""

    kind = "brief"

    def read(self, pm: ProjectManager, project: str, key: str) -> dict[str, Any]:
        data = _load_project(pm, project)
        duration = data.get("target_duration")
        return {
            "brief": _text(data.get("brief")),
            "target_duration": duration
            if isinstance(duration, (int, float)) and not isinstance(duration, bool)
            else None,
        }

    def write(self, pm: ProjectManager, project: str, key: str, changes: dict[str, Any]) -> None:
        updates: dict[str, Any] = {}
        if "brief" in changes:
            updates["brief"] = _text(changes["brief"]).strip()
        if "target_duration" in changes:
            duration = changes["target_duration"]
            if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
                raise UnitWriteError("target_duration_invalid")
            updates["target_duration"] = duration
        if updates:
            _update_project(pm, project, lambda data: data.update(updates))


# ── 资产（角色、场景、道具、商品）────────────────────────────────


class AssetUnit:
    """一个项目资产的文字字段。键为 ``<资产类型>:<名称>``。

    商品卖点在存储里是字符串列表，编辑区里是每行一条的一段文字，读写时互转。
    """

    kind = "asset"

    def read(self, pm: ProjectManager, project: str, key: str) -> dict[str, Any]:
        asset_type, name = _split_asset_key(key)
        entry = _asset_entry(pm, project, asset_type, name)
        fields: dict[str, Any] = {"description": _text(entry.get("description"))}
        if asset_type == "character":
            fields["voice_style"] = _text(entry.get("voice_style"))
        if asset_type == "product":
            fields["brand"] = _text(entry.get("brand"))
            points = entry.get("selling_points")
            fields["selling_points"] = (
                "\n".join(p for p in points if isinstance(p, str)) if isinstance(points, list) else ""
            )
        return fields

    def write(self, pm: ProjectManager, project: str, key: str, changes: dict[str, Any]) -> None:
        asset_type, name = _split_asset_key(key)
        allowed = {"description"} | ({"voice_style"} if asset_type == "character" else set())
        allowed |= {"brand", "selling_points"} if asset_type == "product" else set()
        updates: dict[str, Any] = {}
        for field in allowed & changes.keys():
            value = _text(changes[field])
            updates[field] = _selling_points(value) if field == "selling_points" else value
        if not updates:
            return
        try:
            pm.update_asset_entry(asset_type, project, name, lambda entry: entry.update(updates))
        except (KeyError, FileNotFoundError) as exc:
            raise UnitNotFoundError(key) from exc


# ── 角色衍生形象 ─────────────────────────────────────────────────


class DerivativeUnit:
    """角色衍生形象的描述。键为 ``<角色名>/<衍生名>``（与剧本里引用衍生的写法一致）。"""

    kind = "derivative"

    def read(self, pm: ProjectManager, project: str, key: str) -> dict[str, Any]:
        owner, name = _split_derivative_key(key)
        entry = _asset_entry(pm, project, "character", owner)
        table = derivative_table(entry)
        derivative_key = resolve_asset_key(table, name)
        if derivative_key is None or not isinstance(table[derivative_key], dict):
            raise UnitNotFoundError(key)
        return {"description": _text(table[derivative_key].get("description"))}

    def write(self, pm: ProjectManager, project: str, key: str, changes: dict[str, Any]) -> None:
        if "description" not in changes:
            return
        owner, name = _split_derivative_key(key)
        description = _text(changes["description"])

        def _mutate(entry: dict[str, Any]) -> None:
            table = ensure_derivative_table(entry)
            derivative_key = resolve_asset_key(table, name)
            if derivative_key is None or not isinstance(table[derivative_key], dict):
                raise KeyError(name)
            table[derivative_key]["description"] = description

        try:
            pm.update_asset_entry("character", project, owner, _mutate)
        except (KeyError, FileNotFoundError) as exc:
            raise UnitNotFoundError(key) from exc


# ── 自带原文的集 ─────────────────────────────────────────────────


class EpisodeSourceUnit:
    """一集自己的原文（集页填写或上传的那份）。键为集 ID。切自整本源文的集由分集规划派生，不能在这里改。

    原文类型（小说 / 剧本）会让已开始制作的集需要确认，不放进协作内容，仍由编辑区单独提交。
    """

    kind = "episode_source"

    def read(self, pm: ProjectManager, project: str, key: str) -> dict[str, Any]:
        episode = _episode_number(key)
        data = _load_project(pm, project)
        entry = _episode_entry(data, episode)
        if entry is None:
            raise UnitNotFoundError(key)
        path = episode_source_path(pm.get_project_path(project), episode)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = ""
        except (OSError, UnicodeDecodeError) as exc:
            raise UnitNotFoundError(key) from exc
        return {"text": text}

    def write(self, pm: ProjectManager, project: str, key: str, changes: dict[str, Any]) -> None:
        if "text" not in changes:
            return
        try:
            set_episode_source_text(pm, project, _episode_number(key), _text(changes["text"]))
        except EpisodeSourceError as exc:
            if exc.code == "episode_not_found":
                raise UnitNotFoundError(key) from exc
            raise UnitWriteError(exc.code, str(exc)) from exc
        except FileNotFoundError as exc:
            raise UnitNotFoundError(key) from exc


# ── 剧本里的一格（旁白段落、剧情场景、广告分镜、参考视频单元）────────

#: 剧本集合 → (编号字段, 可以协作编辑的字段)。白名单与各自的 REST PATCH 一致。
_SCRIPT_COLLECTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "segments": (
        "segment_id",
        (
            "duration_seconds",
            "segment_break",
            "novel_text",
            "image_prompt",
            "video_prompt",
            "note",
            "characters_in_segment",
            "scenes",
            "props",
        ),
    ),
    "scenes": (
        "scene_id",
        (
            "duration_seconds",
            "image_prompt",
            "video_prompt",
            "characters_in_scene",
            "scenes",
            "props",
            "segment_break",
            "utterances",
            "note",
        ),
    ),
    "shots": (
        "shot_id",
        (
            "section",
            "voiceover_text",
            "duration_seconds",
            "image_prompt",
            "video_prompt",
            "characters_in_shot",
            "scenes",
            "props",
            "products_in_shot",
            "note",
        ),
    ),
    "video_units": ("unit_id", ("text", "duration_seconds", "note")),
}

#: 引用资产名的列表字段：写入前按资产名比较键规范化，与 REST 一致。
_ASSET_LIST_FIELDS = frozenset(
    {"characters_in_segment", "characters_in_scene", "characters_in_shot", "scenes", "props", "products_in_shot"}
)


class ScriptItemUnit:
    """剧本里的一格。键为 ``<剧本文件>#<编号>``。

    内容是该格在白名单里、实际存在的字段；写回走剧本批量编辑的 ``update``，与各分镜接口同一条路径。
    """

    kind = "script_item"

    def read(self, pm: ProjectManager, project: str, key: str) -> dict[str, Any]:
        script_file, item_id = _split_script_key(key)
        script = _load_script(pm, project, script_file)
        located = _locate_item(script, item_id)
        if located is None:
            raise UnitNotFoundError(key)
        item, fields = located
        return {field: item[field] for field in fields if field in item}

    def write(self, pm: ProjectManager, project: str, key: str, changes: dict[str, Any]) -> None:
        script_file, item_id = _split_script_key(key)
        for _attempt in range(2):
            script = _load_script(pm, project, script_file)
            located = _locate_item(script, item_id)
            if located is None:
                raise UnitNotFoundError(key)
            _item, allowed = located
            fields = {field: _normalize_list(field, value) for field, value in changes.items() if field in allowed}
            if not fields:
                return
            command = ScriptBatchEditCommand.model_validate(
                {
                    "script": script_file,
                    # 剧本锁里比对这份修订号：读与写之间有别人改了同一份剧本时拒绝，下面重读一次再写
                    "expected_revision": script_revision(script),
                    "operations": [{"op": "update", "id": item_id, "fields": fields}],
                }
            )
            result = ScriptBatchEditor(pm).execute(project, command)
            if result.success:
                return
            problem = result.problems[0]
            if problem.code == "revision_conflict":
                continue
            raise UnitWriteError(problem.code, problem.reason)
        raise UnitWriteError("revision_conflict")


# ── 共用 ─────────────────────────────────────────────────────────


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _load_project(pm: ProjectManager, project: str) -> dict[str, Any]:
    try:
        return pm.load_project(project)
    except FileNotFoundError as exc:
        raise UnitNotFoundError(project) from exc


def _update_project(pm: ProjectManager, project: str, mutate: Any) -> None:
    try:
        pm.update_project(project, mutate)
    except FileNotFoundError as exc:
        raise UnitNotFoundError(project) from exc


def _split_asset_key(key: str) -> tuple[str, str]:
    asset_type, sep, name = key.partition(":")
    if not sep or asset_type not in ASSET_SPECS or not name:
        raise UnitNotFoundError(key)
    return asset_type, name


def _split_derivative_key(key: str) -> tuple[str, str]:
    owner, sep, name = key.partition("/")
    if not sep or not owner or not name:
        raise UnitNotFoundError(key)
    return owner, name


def _split_script_key(key: str) -> tuple[str, str]:
    script_file, sep, item_id = key.rpartition("#")
    if not sep or not script_file or not item_id:
        raise UnitNotFoundError(key)
    return script_file, item_id


def _episode_number(key: str) -> int:
    try:
        episode = int(key)
    except ValueError as exc:
        raise UnitNotFoundError(key) from exc
    if episode <= 0:
        raise UnitNotFoundError(key)
    return episode


def _asset_entry(pm: ProjectManager, project: str, asset_type: str, name: str) -> dict[str, Any]:
    data = _load_project(pm, project)
    bucket = data.get(ASSET_SPECS[asset_type].bucket_key)
    entry_key = resolve_asset_key(bucket, name) if isinstance(bucket, dict) else None
    entry = bucket.get(entry_key) if isinstance(bucket, dict) and entry_key is not None else None
    if not isinstance(entry, dict):
        raise UnitNotFoundError(name)
    return entry


def _episode_entry(data: dict[str, Any], episode: int) -> dict[str, Any] | None:
    episodes = data.get("episodes")
    for entry in episodes if isinstance(episodes, list) else []:
        if isinstance(entry, dict) and parse_positive_episode_num(entry.get("episode")) == episode:
            return entry
    return None


def _load_script(pm: ProjectManager, project: str, script_file: str) -> dict[str, Any]:
    try:
        return pm.load_script(project, script_file)
    except (FileNotFoundError, ValueError) as exc:
        raise UnitNotFoundError(script_file) from exc


def _locate_item(script: dict[str, Any], item_id: str) -> tuple[dict[str, Any], tuple[str, ...]] | None:
    for collection, (id_field, fields) in _SCRIPT_COLLECTIONS.items():
        items = script.get(collection)
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and item.get(id_field) == item_id:
                return item, fields
    return None


def _normalize_list(field: str, value: Any) -> Any:
    if field in _ASSET_LIST_FIELDS and isinstance(value, list):
        return [asset_name_comparison_key(entry) if isinstance(entry, str) else entry for entry in value]
    return value


def _selling_points(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


# ── 页面在线状态 ─────────────────────────────────────────────────


class PageUnit:
    """一个项目页面上的在线状态（谁在、鼠标指在哪）。文档没有内容，只借房间转发在线状态，不写回任何东西。

    键是页面路径（不含查询串），只用来把看同一页的人放进同一个房间。
    """

    kind = "page"

    def read(self, pm: ProjectManager, project: str, key: str) -> dict[str, Any]:
        if not key.startswith("/") or not pm.project_exists(project):
            raise UnitNotFoundError(key)
        return {}

    def write(self, pm: ProjectManager, project: str, key: str, changes: dict[str, Any]) -> None:
        # 页面房间不承载内容，浏览器也不会往文档里写；有人硬塞内容也不落盘
        return


# ── 项目设置 ─────────────────────────────────────────────────────

#: 只读、跟着上传或清除变化的字段：浏览器写来的值不落盘，清空参考图除外
_SETTINGS_DERIVED_FIELDS = ("style_image", "style_description")
_SETTINGS_FIELDS = tuple(f for f in ProjectSettingsPatch.model_fields if f != "clear_style_image")


class ProjectSettingsUnit:
    """项目设置页（基础、风格、模型、配音）：字段名与项目文件、项目 PATCH 一致，写回走同一套校验。"""

    kind = "project_settings"

    def read(self, pm: ProjectManager, project: str, key: str) -> dict[str, Any]:
        data = _load_project(pm, project)
        return {field: data.get(field) for field in (*_SETTINGS_FIELDS, *_SETTINGS_DERIVED_FIELDS)}

    def write(self, pm: ProjectManager, project: str, key: str, changes: dict[str, Any]) -> None:
        values = {f: changes[f] for f in _SETTINGS_FIELDS if f in changes}
        # 参考图只能经上传换掉；房间里清空它即取消参考图
        if "style_image" in changes and not changes["style_image"]:
            values["clear_style_image"] = True
        if not values:
            return
        try:
            patch = ProjectSettingsPatch.model_validate(values)
        except ValidationError as exc:
            raise UnitWriteError("invalid_settings", str(exc)) from exc

        def _mutate(data: dict) -> None:
            apply_project_settings_patch(data, patch)

        try:
            _update_project(pm, project, _mutate)
        except ApiError as exc:
            raise UnitWriteError(exc.key, params=exc.params) from exc


# ── Agent 记忆文件 ───────────────────────────────────────────────


def _memory_text(store: AgentMemoryStore, filename: str) -> dict[str, Any]:
    try:
        raw = store.read(filename)
    except ApiError as exc:
        raise UnitNotFoundError(filename) from exc
    # 记忆由 Agent 自由书写，可能混入非 UTF-8 字节：按替换字符显示，编辑后以 UTF-8 写回
    return {"content": raw.decode("utf-8", errors="replace")}


def _write_memory_text(store: AgentMemoryStore, filename: str, changes: dict[str, Any]) -> None:
    if "content" not in changes:
        return
    try:
        store.write(filename, _text(changes["content"]).encode("utf-8"))
    except ApiError as exc:
        raise UnitWriteError(exc.key, params=exc.params) from exc


class ProjectMemoryFileUnit:
    """项目记忆里的一个文件，键是文件名；内容只有一段正文。"""

    kind = "project_memory_file"

    def read(self, pm: ProjectManager, project: str, key: str) -> dict[str, Any]:
        return _memory_text(self._store(pm, project), key)

    def write(self, pm: ProjectManager, project: str, key: str, changes: dict[str, Any]) -> None:
        _write_memory_text(self._store(pm, project), key, changes)

    @staticmethod
    def _store(pm: ProjectManager, project: str) -> AgentMemoryStore:
        try:
            return AgentMemoryStore.for_project(pm.get_project_path(project))
        except (FileNotFoundError, ValueError) as exc:
            raise UnitNotFoundError(project) from exc


def _workspace_memory_store() -> AgentMemoryStore:
    from lib.project.project_manager import get_project_manager

    # 工作区共用一份用户记忆（与 Agent 读的同一个目录）
    return AgentMemoryStore(get_project_manager().layout.user_memory_dir(DEFAULT_USER_ID))


class WorkspaceMemoryFileUnit:
    """工作区记忆（设置页的「用户记忆」）里的一个文件，不属于任何项目。"""

    kind = "workspace_memory_file"
    scope: Literal["global"] = "global"

    def __init__(self, store: Callable[[], AgentMemoryStore] = _workspace_memory_store) -> None:
        self._store = store

    async def read(self, key: str) -> dict[str, Any]:
        return await run_sync_transaction(lambda: _memory_text(self._store(), key))

    async def write(self, key: str, changes: dict[str, Any]) -> None:
        await run_sync_transaction(lambda: _write_memory_text(self._store(), key, changes))


# ── 全局资产库条目 ───────────────────────────────────────────────


class LibraryAssetUnit:
    """全局资产库的一个条目（键是条目 id）：名称、描述、声音风格。图片与衍生另有接口。"""

    kind = "library_asset"
    scope: Literal["global"] = "global"

    def __init__(self, session_factory: Callable[[], Any] | None = None) -> None:
        self._session_factory = session_factory

    def _sessions(self) -> Any:
        if self._session_factory is not None:
            return self._session_factory()
        from lib.db import async_session_factory

        return async_session_factory()

    async def read(self, key: str) -> dict[str, Any]:
        async with self._sessions() as session:
            asset = await AssetRepository(session).get_by_id(key)
        if asset is None:
            raise UnitNotFoundError(key)
        return {field: getattr(asset, field) or "" for field in LIBRARY_ASSET_TEXT_FIELDS}

    async def write(self, key: str, changes: dict[str, Any]) -> None:
        values = {field: _text(changes[field]) for field in LIBRARY_ASSET_TEXT_FIELDS if field in changes}
        if not values:
            return
        async with self._sessions() as session:
            try:
                await update_library_asset_fields(session, key, values)
            except NotFoundError as exc:
                raise UnitNotFoundError(key) from exc
            except ApiError as exc:
                raise UnitWriteError(exc.key, params=exc.params) from exc


#: 属于项目的单元：读写是同步的文件操作
PROJECT_UNIT_SPECS: dict[str, UnitSpec] = {
    spec.kind: spec
    for spec in (
        PageUnit(),
        OverviewUnit(),
        BriefUnit(),
        AssetUnit(),
        DerivativeUnit(),
        EpisodeSourceUnit(),
        ScriptItemUnit(),
        ProjectSettingsUnit(),
        ProjectMemoryFileUnit(),
    )
}

#: 不属于项目的单元：房间的 project 为空串
GLOBAL_UNIT_SPECS: dict[str, GlobalUnitSpec] = {
    spec.kind: spec for spec in (WorkspaceMemoryFileUnit(), LibraryAssetUnit())
}

UNIT_SPECS: dict[str, AnyUnitSpec] = {**PROJECT_UNIT_SPECS, **GLOBAL_UNIT_SPECS}
