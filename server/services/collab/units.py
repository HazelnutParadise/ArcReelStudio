"""可以多人同时编辑的「编辑单元」：每种单元怎么从项目文件读出、改了之后怎么写回。

一个单元对应界面上的一个编辑区（项目概述、某个角色、某一格分镜……）。协作文档的内容就是 :meth:`UnitSpec.read`
返回的对象（存储里的字段，按白名单挑出），写回时只交出改动过的顶层字段，走与 REST 接口同一套修改逻辑。

读写都是同步的文件操作，由调用方放进线程执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from lib.episode.episode_ledger import parse_positive_episode_num
from lib.episode.episode_paths import episode_source_path
from lib.episode.episode_source_commands import EpisodeSourceError, set_episode_source_text
from lib.project.asset_derivatives import derivative_table, ensure_derivative_table
from lib.project.asset_types import ASSET_SPECS, asset_name_comparison_key, resolve_asset_key
from lib.project.project_manager import ProjectManager
from lib.script.script_batch_edit import ScriptBatchEditCommand, ScriptBatchEditor, script_revision


class UnitNotFoundError(LookupError):
    """单元已不存在（项目、角色或分镜被删除或改名）。"""


class UnitWriteError(ValueError):
    """内容不合规，不能写回；``code`` 是给界面本地化用的稳定键。"""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class UnitRef:
    project: str
    kind: str
    key: str


class UnitSpec(Protocol):
    kind: str

    def read(self, pm: ProjectManager, project: str, key: str) -> dict[str, Any]:
        """单元当前的内容；不存在时抛 :class:`UnitNotFoundError`。"""
        ...

    def write(self, pm: ProjectManager, project: str, key: str, changes: dict[str, Any]) -> None:
        """写回改动过的顶层字段；内容不合规时抛 :class:`UnitWriteError`。"""
        ...


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


UNIT_SPECS: dict[str, UnitSpec] = {
    spec.kind: spec
    for spec in (
        PageUnit(),
        OverviewUnit(),
        BriefUnit(),
        AssetUnit(),
        DerivativeUnit(),
        EpisodeSourceUnit(),
        ScriptItemUnit(),
    )
}
