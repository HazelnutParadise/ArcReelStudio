"""Codex 引擎的文件工具：Read、Write、Edit、Glob、Grep。

Codex 自带的 shell、命令执行与改档工具在 ArcReel 里全部关闭（它的沙箱在容器里起不来，也挡不住读数据根下的凭证），
文件读写改由这里的 dynamic tools 提供，并且与 Claude 引擎走同一套访问规则：每次调用先经
:meth:`server.agent_runtime.agent_access_policy.AgentAccessPolicy.check_path_access`（Claude 引擎的 PreToolUse
hook 用的也是它），被拒时回失败与拒绝说明，不碰文件。

结果格式是 Codex ``item/tool/call`` 的回应：``{"contentItems": [{"type": "inputText", "text": ...}], "success": bool}``。
工具名与参数名照 Claude Code 的同名工具（前端按 ``Read``/``Edit`` 的 ``file_path``、``Glob``/``Grep`` 的 ``path`` 摘要）。
"""

from __future__ import annotations

import asyncio
import fnmatch
import re
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


class _ArgumentError(Exception):
    """参数缺失或型别不符；由 :meth:`CodexFileTools.call` 转成失败结果，不冒泡给调用方。"""


def _require_str(arguments: Mapping[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str):
        raise _ArgumentError(f"参数 {key} 缺失或类型不正确（需要字符串）")
    return value


def _optional_str(arguments: Mapping[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _ArgumentError(f"参数 {key} 类型不正确（需要字符串）")
    return value


def _optional_positive_int(arguments: Mapping[str, Any], key: str, default: int) -> int:
    value = arguments.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _ArgumentError(f"参数 {key} 必须是正整数")
    return value


def _optional_bool(arguments: Mapping[str, Any], key: str, default: bool) -> bool:
    value = arguments.get(key, default)
    if not isinstance(value, bool):
        raise _ArgumentError(f"参数 {key} 必须是布尔值")
    return value


def _tool_result(*, success: bool, text: str) -> dict[str, Any]:
    return {"contentItems": [{"type": "inputText", "text": text}], "success": success}


def _success(text: str) -> dict[str, Any]:
    return _tool_result(success=True, text=text)


def _failure(text: str) -> dict[str, Any]:
    return _tool_result(success=False, text=text)


def _display_path(path: Path, project_cwd: Path) -> str:
    """相对 ``project_cwd`` 的路径；不在其下时回绝对路径。"""
    try:
        return path.relative_to(project_cwd).as_posix()
    except ValueError:
        return str(path)


def _read_lines(target: Path, offset: int, limit: int) -> tuple[str, str | None]:
    """同步读文件并格式化为 ``行号\\t内容``；回 ``(text, error)``，error 非 None 表示失败。"""
    try:
        content = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "", f"文件不存在 (not found): {target}"
    except IsADirectoryError:
        return "", f"不是文件: {target}"
    except UnicodeDecodeError:
        return "", f"不是 UTF-8 文本（可能是二进制文件或编码不支持）: {target}"
    except OSError as exc:
        return "", f"读取失败: {exc}"
    lines = content.splitlines()
    selected = lines[offset - 1 : offset - 1 + limit]
    text = "\n".join(
        f"{line_number}\t{line[:READ_MAX_LINE_CHARS]}" for line_number, line in enumerate(selected, start=offset)
    )
    return text, None


def _write_file(target: Path, content: str) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已写入 {len(content)} 个字符: {target}"


def _edit_file(target: Path, old_string: str, new_string: str, replace_all: bool) -> tuple[str, str | None]:
    """同步执行 Edit；回 ``(text, error)``，error 非 None 表示失败。"""
    try:
        content = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "", f"文件不存在 (not found): {target}"
    except IsADirectoryError:
        return "", f"不是文件: {target}"
    except UnicodeDecodeError:
        return "", f"不是 UTF-8 文本（可能是二进制文件或编码不支持）: {target}"
    except OSError as exc:
        return "", f"读取失败: {exc}"
    count = content.count(old_string)
    if count == 0:
        return "", f"old_string 不存在: {old_string!r}"
    if count > 1 and not replace_all:
        return "", f"old_string 出现 {count} 次，请提供更多上下文或设置 replace_all=true"
    updated = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
    try:
        target.write_text(updated, encoding="utf-8")
    except OSError as exc:
        return "", f"写入失败: {exc}"
    return f"已替换 {count} 处: {target}", None


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
        if tool not in FILE_TOOL_NAMES:
            return _failure(f"tool {tool} not found")
        try:
            if tool == "Read":
                return await self._read(arguments)
            if tool == "Write":
                return await self._write(arguments)
            if tool == "Edit":
                return await self._edit(arguments)
            if tool == "Glob":
                return await self._glob(arguments)
            if tool == "Grep":
                return await self._grep(arguments)
        except _ArgumentError as exc:
            return _failure(str(exc))
        return _failure(f"tool {tool} not found")

    def _target_path(self, raw_path: str) -> Path:
        """相对路径以 ``project_cwd`` 为基准，绝对路径原样使用。纯路径拼接，不碰文件系统。"""
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return self.project_cwd / path

    async def _deny_message(self, raw_path: str, tool: str) -> str | None:
        """在 worker thread 里跑 ``check_path_access``（它内部会 resolve，属文件系统 I/O）。"""
        allowed, reason = await asyncio.to_thread(
            self.policy.check_path_access,
            raw_path,
            tool,
            self.project_cwd,
            user_id=self.user_id,
        )
        if allowed:
            return None
        return reason or "访问被拒绝"

    async def _read(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        raw_path = _require_str(arguments, "file_path")
        offset = _optional_positive_int(arguments, "offset", 1)
        limit = _optional_positive_int(arguments, "limit", READ_DEFAULT_LIMIT)
        denied = await self._deny_message(raw_path, "Read")
        if denied is not None:
            return _failure(denied)
        target = self._target_path(raw_path)
        try:
            text, error = await asyncio.to_thread(_read_lines, target, offset, limit)
        except OSError as exc:
            return _failure(f"读取失败: {exc}")
        if error is not None:
            return _failure(error)
        return _success(text)

    async def _write(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        raw_path = _require_str(arguments, "file_path")
        content = _require_str(arguments, "content")
        denied = await self._deny_message(raw_path, "Write")
        if denied is not None:
            return _failure(denied)
        target = self._target_path(raw_path)
        try:
            text = await asyncio.to_thread(_write_file, target, content)
        except OSError as exc:
            return _failure(f"写入失败: {exc}")
        return _success(text)

    async def _edit(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        raw_path = _require_str(arguments, "file_path")
        old_string = _require_str(arguments, "old_string")
        new_string = _require_str(arguments, "new_string")
        replace_all = _optional_bool(arguments, "replace_all", False)
        if not old_string:
            return _failure("old_string 不能为空")
        if old_string == new_string:
            return _failure("old_string 与 new_string 相同，没有可替换的内容")
        denied = await self._deny_message(raw_path, "Edit")
        if denied is not None:
            return _failure(denied)
        target = self._target_path(raw_path)
        try:
            text, error = await asyncio.to_thread(_edit_file, target, old_string, new_string, replace_all)
        except OSError as exc:
            return _failure(f"写入失败: {exc}")
        if error is not None:
            return _failure(error)
        return _success(text)

    async def _glob(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        pattern = _require_str(arguments, "pattern")
        raw_path = _optional_str(arguments, "path")
        search_root = raw_path if raw_path is not None else str(self.project_cwd)
        denied = await self._deny_message(search_root, "Glob")
        if denied is not None:
            return _failure(denied)
        root = self._target_path(search_root)
        try:
            paths, error = await asyncio.to_thread(self._collect_glob, root, pattern)
        except OSError as exc:
            return _failure(f"查找失败: {exc}")
        if error is not None:
            return _failure(error)
        if not paths:
            return _success("没有找到匹配的文件")
        return _success("\n".join(paths))

    async def _grep(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        pattern = _require_str(arguments, "pattern")
        raw_path = _optional_str(arguments, "path")
        glob_pattern = _optional_str(arguments, "glob")
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return _failure(f"无效的正则表达式: {exc}")
        search_root = raw_path if raw_path is not None else str(self.project_cwd)
        denied = await self._deny_message(search_root, "Grep")
        if denied is not None:
            return _failure(denied)
        root = self._target_path(search_root)
        try:
            matches, error = await asyncio.to_thread(self._collect_grep, root, regex, glob_pattern)
        except OSError as exc:
            return _failure(f"搜索失败: {exc}")
        if error is not None:
            return _failure(error)
        if not matches:
            return _success("没有找到匹配的内容")
        return _success("\n".join(matches))

    def _collect_glob(self, root: Path, pattern: str) -> tuple[list[str], str | None]:
        """同步枚举 Glob 结果（在 worker thread 执行）：按 mtime 新到旧排序、过滤 policy 拒绝项。"""
        try:
            candidates = list(root.glob(pattern))
        except (ValueError, NotImplementedError, OSError) as exc:
            return [], f"无效的 glob 模式: {exc}"
        matched: list[tuple[float, str]] = []
        for candidate in candidates:
            if not candidate.is_file():
                continue
            allowed, _reason = self.policy.check_path_access(
                str(candidate), "Read", self.project_cwd, user_id=self.user_id
            )
            if not allowed:
                continue
            try:
                mtime = candidate.stat().st_mtime
            except OSError:
                mtime = 0.0
            matched.append((mtime, _display_path(candidate, self.project_cwd)))
        matched.sort(key=lambda item: item[0], reverse=True)
        return [path for _, path in matched[:SEARCH_MAX_RESULTS]], None

    def _collect_grep(
        self, root: Path, regex: re.Pattern[str], glob_pattern: str | None
    ) -> tuple[list[str], str | None]:
        """同步枚举 Grep 结果（在 worker thread 执行）：略过二进制、非 UTF-8 与 policy 拒绝的文件。"""
        try:
            if root.is_file():
                files = [root]
            elif root.is_dir():
                files = sorted(path for path in root.rglob("*") if path.is_file())
            else:
                return [], None
        except OSError as exc:
            return [], f"搜索失败: {exc}"
        matches: list[str] = []
        for file in files:
            if glob_pattern is not None and not fnmatch.fnmatchcase(file.name, glob_pattern):
                continue
            allowed, _reason = self.policy.check_path_access(str(file), "Grep", self.project_cwd, user_id=self.user_id)
            if not allowed:
                continue
            try:
                content = file.read_text(encoding="utf-8")
            except UnicodeDecodeError, OSError:
                continue
            display = _display_path(file, self.project_cwd)
            for line_number, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{display}:{line_number}:{line}")
                    if len(matches) >= SEARCH_MAX_RESULTS:
                        return matches, None
        return matches, None
