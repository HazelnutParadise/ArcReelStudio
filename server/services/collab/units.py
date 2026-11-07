"""可以多人同时编辑的「编辑单元」：每种单元怎么从项目文件读出、改了之后怎么写回。

一个单元对应界面上的一个编辑区（项目概述、某个角色、某一格分镜……）。协作文档的内容就是 :meth:`UnitSpec.read`
返回的对象（存储里的字段，按白名单挑出），写回时只交出改动过的顶层字段，走与 REST 接口同一套修改逻辑。

读写都是同步的文件操作，由调用方放进线程执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from lib.project.project_manager import ProjectManager


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
        try:
            data = pm.load_project(project)
        except FileNotFoundError as exc:
            raise UnitNotFoundError(project) from exc
        overview = data.get("overview") if isinstance(data.get("overview"), dict) else {}
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


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


UNIT_SPECS: dict[str, UnitSpec] = {spec.kind: spec for spec in (OverviewUnit(),)}
