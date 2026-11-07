"""HTTP compatibility adapters for the shared episode-script edit command."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from fastapi import HTTPException

from lib.infra.api_errors import ConflictError
from lib.project.asset_types import asset_name_comparison_key
from lib.project.project_manager import ProjectManager
from lib.script.script_batch_edit import (
    ScriptBatchEditCommand,
    ScriptBatchEditor,
    ScriptBatchEditResult,
    script_revision,
)

_SPEECH_PROBLEM_CODES = frozenset({"mixed_speech", "needs_replan", "parse_failed", "empty_speaker"})

#: 引用资产名的列表字段：按资产名比较键核对，与写入时的规范化一致。
_ASSET_REFERENCE_FIELDS = frozenset(
    {"characters_in_segment", "characters_in_scene", "characters_in_shot", "scenes", "props"}
)


def _comparable(field: str, value: Any) -> str:
    # 缺字段、空串、空列表、0 与 false 视为同一个「空」：编辑器把缺省字段显示成空值，起点里就是这些值。
    if not value:
        return "null"
    if field in _ASSET_REFERENCE_FIELDS and isinstance(value, list):
        value = [asset_name_comparison_key(entry) if isinstance(entry, str) else entry for entry in value]
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def require_fields_unchanged(
    item: Mapping[str, Any], fields: Mapping[str, Any], base: Mapping[str, Any] | None
) -> None:
    """核对这次要写的字段在编辑起点之后没有被改过，被改过时抛 409，不覆盖别人的修改。

    ``base`` 是客户端开始编辑时看到的值，只核对 ``fields`` 里出现的字段；剧本里没有的字段与各种空值视为相同。
    不带 ``base`` 的旧请求不核对。调用方须把同一份剧本作为 ``current_script`` 交给写入，
    让写入时的 revision 覆盖这次核对读到的内容。
    """
    if not base:
        return
    stale = [
        field
        for field in fields
        if field in base and _comparable(field, item.get(field)) != _comparable(field, base[field])
    ]
    if stale:
        raise ConflictError("edit_conflict").with_diagnostic({"code": "edit_conflict", "fields": stale})


class ScriptEditExecutor(Protocol):
    def execute(self, project_name: str, command: ScriptBatchEditCommand) -> ScriptBatchEditResult:
        raise NotImplementedError


def script_batch_status(result: ScriptBatchEditResult) -> int:
    if result.success:
        return 200
    code = result.problems[0].code
    if code == "revision_conflict" or code in _SPEECH_PROBLEM_CODES:
        return 409
    if code == "commit_failed":
        return 500
    return 422


def execute_current_script_edit(
    manager: ProjectManager,
    project_name: str,
    script_file: str,
    operations: Sequence[Mapping[str, Any]],
    *,
    editor: ScriptEditExecutor | None = None,
    current_script: Mapping[str, Any] | None = None,
) -> ScriptBatchEditResult:
    """Adapt an unversioned legacy request to one revisioned command.

    The revision is only a compatibility snapshot. The editor still compares it inside
    the project lock, so a concurrent writer is rejected instead of being overwritten.
    Callers that derived the operations from a script they already loaded pass it as
    ``current_script`` so the revision covers that same snapshot.
    """

    current = manager.load_script(project_name, script_file) if current_script is None else current_script
    command = ScriptBatchEditCommand.model_validate(
        {
            "script": script_file,
            "expected_revision": script_revision(current),
            "operations": list(operations),
        }
    )
    return (editor or ScriptBatchEditor(manager)).execute(project_name, command)


def execute_current_episode_edit(
    manager: ProjectManager,
    project_name: str,
    episode: int,
    script_file: str,
    current_script: Mapping[str, Any],
    operations: Sequence[Mapping[str, Any]],
) -> ScriptBatchEditResult:
    """Adapt an episode-scoped legacy request while retaining binding TOCTOU checks."""

    command = ScriptBatchEditCommand.model_validate(
        {
            "episode": episode,
            "expected_script_file": script_file,
            "expected_revision": script_revision(current_script),
            "operations": list(operations),
        }
    )
    return ScriptBatchEditor(manager).execute(project_name, command)


def require_script_edit_result(
    result: ScriptBatchEditResult,
    *,
    operation_not_found: bool = False,
) -> None:
    if result.success:
        return
    first = result.problems[0]
    status_code = script_batch_status(result)
    if first.code == "operation_invalid" and operation_not_found:
        status_code = 404
    elif first.code == "references_invalid":
        status_code = 400
    raise HTTPException(status_code=status_code, detail=result.model_dump(mode="json"))


__all__ = [
    "execute_current_episode_edit",
    "execute_current_script_edit",
    "require_fields_unchanged",
    "require_script_edit_result",
    "script_batch_status",
]
