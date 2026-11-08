"""Codex 引擎的文件工具：Read、Write、Edit、Glob、Grep。

Codex 自带的 shell、命令执行与改档工具在 ArcReel 里全部关闭（它的沙箱在容器里起不来，也挡不住读数据根下的凭证），
文件读写改由这里的 dynamic tools 提供，并且与 Claude 引擎走同一套访问规则：每次调用先经
:meth:`server.agent_runtime.agent_access_policy.AgentAccessPolicy.check_path_access`（Claude 引擎的 PreToolUse
hook 用的也是它），被拒时回失败与拒绝说明，不碰文件。

结果格式是 Codex ``item/tool/call`` 的回应：``{"contentItems": [{"type": "inputText", "text": ...}], "success": bool}``。
工具名与参数名照 Claude Code 的同名工具（前端按 ``Read``/``Edit`` 的 ``file_path``、``Glob``/``Grep`` 的 ``path`` 摘要）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from server.agent_runtime.agent_access_policy import AgentAccessPolicy

#: Read 默认最多读多少行；单行超过这个长度截断
READ_DEFAULT_LIMIT = 2000
READ_MAX_LINE_CHARS = 2000
#: Glob / Grep 最多回多少条
SEARCH_MAX_RESULTS = 200

#: ``thread/start.dynamicTools`` 的文件工具清单（JSON Schema 照 Claude Code 同名工具的参数）
FILE_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "Read",
        "description": "Read a text file. Lines are returned as `<line number>\\t<text>`. Use offset/limit for long files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path relative to the project, or absolute"},
                "offset": {"type": "integer", "minimum": 1, "description": "1-based line to start from"},
                "limit": {"type": "integer", "minimum": 1, "description": "Number of lines to read"},
            },
            "required": ["file_path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "Write",
        "description": "Create or overwrite a text file with the given content.",
        "inputSchema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["file_path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "Edit",
        "description": "Replace an exact string in a text file. old_string must be unique unless replace_all is true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
            },
            "required": ["file_path", "old_string", "new_string"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "Glob",
        "description": "Find files matching a glob pattern (e.g. `**/*.md`) under path (default: the project).",
        "inputSchema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "Grep",
        "description": "Search file contents with a regular expression under path (default: the project). "
        "Returns `<file>:<line number>:<line>` matches.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "glob": {"type": "string", "description": "Only search files whose name matches this glob"},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
    },
]

FILE_TOOL_NAMES = frozenset(spec["name"] for spec in FILE_TOOL_SPECS)


@dataclass(frozen=True)
class CodexFileTools:
    """一个会话的文件工具：``project_cwd`` 是会话项目目录，相对路径以它为基准。"""

    policy: AgentAccessPolicy
    project_cwd: Path
    user_id: str

    async def call(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """执行文件工具并回 Codex 的工具结果。

        想要的结果：
        - 未知工具名 → success False，文字含 "not found"。
        - 参数缺少必填键或型别不对（例如 file_path 不是字串）→ success False，文字说明哪个参数有问题，不抛例外。
        - 每次先以 ``policy.check_path_access(<路径>, tool, project_cwd, user_id=user_id)`` 检查：Read/Write/Edit 检查
          ``file_path``；Glob/Grep 检查 ``path``（没给时用 project_cwd）。被拒 → success False，文字是拒绝说明，
          文件系统不得有任何变动。
        - 相对路径以 project_cwd 为基准。
        - Read：文件不存在 → success False 说明找不到；成功时每行格式为 ``f"{行号}\\t{内容}"``（行号从 1 起，配合 offset），
          只回 offset 起 limit 行（默认 READ_DEFAULT_LIMIT），单行超过 READ_MAX_LINE_CHARS 截断；文件不是 UTF-8 文字 →
          success False 说明是二进制或编码不支持。
        - Write：建立缺少的上层目录，整份写入（UTF-8），回成功说明（含写入的字元数）。
        - Edit：文件不存在 → 失败；old_string 不存在 → 失败；old_string 出现多次且 replace_all 不为 True → 失败并说明出现几次；
          old_string 等于 new_string → 失败；成功时写回并说明替换了几处。
        - Glob：在 path 之下找符合 pattern 的文件（``Path.glob``），回相对于 project_cwd 的路径（不在 project_cwd 下时回绝对路径），
          依修改时间新到旧排序，每行一个，最多 SEARCH_MAX_RESULTS 条；没有符合 → success True、文字说明没有找到。
        - Grep：pattern 是 Python 正规表示式（无效时 success False 说明）；在 path 之下（是档案就只搜它）逐个文字档逐行比对，
          glob 给了时只搜文件名符合的；略过二进制与非 UTF-8 文件；回 ``f"{相对路径}:{行号}:{行内容}"``，最多 SEARCH_MAX_RESULTS 条；
          Glob 与 Grep 列出的每个文件也要通过 ``check_path_access``（以 Read/Grep 名义），被拒的文件直接略过、不出现在结果里。
        - 所有文件 I/O 都在 ``asyncio.to_thread`` 里做，不在事件循环上阻塞。
        """
        raise NotImplementedError
