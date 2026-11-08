"""CodexFileTools.call 的行为测试：Read、Write、Edit、Glob、Grep。

每个用例都走真的 :class:`AgentAccessPolicy`，逐条对照 ``CodexFileTools.call`` docstring：
未知工具、参数校验、路径围栏、Read 行号/offset/limit/截断/编码、Write 建目录与拒绝、
Edit 的替换与出现次数、Glob 的相对路径与排序、Grep 的 ``档案:行号:内容`` 与 policy 过滤。

结果一律从 Codex ``item/tool/call`` 的 envelope 取文字：``{"contentItems": [...], "success": bool}``。
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import pytest

from lib.infra.data_root_layout import DataRootLayout
from server.agent_runtime.agent_access_policy import AgentAccessPolicy
from server.agent_runtime.codex_file_tools import (
    READ_DEFAULT_LIMIT,
    READ_MAX_LINE_CHARS,
    SEARCH_MAX_RESULTS,
    CodexFileTools,
)

#: 逐调用传入的当前用户 id（生产取自 SessionManager 的 CurrentUser 上下文）。
_USER_ID = "default"


def _text(result: dict[str, object]) -> str:
    """把 Codex 工具结果的 inputText 区块拼成一段文字。"""
    items = result.get("contentItems")
    if not isinstance(items, list):
        return ""
    return "\n".join(str(item.get("text", "")) for item in items if isinstance(item, dict))


def _projects_dir(policy: AgentAccessPolicy) -> Path:
    return DataRootLayout(policy.data_root).projects_dir


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_numbered_files(directory: Path, count: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (directory / f"file-{index:03d}.txt").write_text("x", encoding="utf-8")


@pytest.fixture
def access_policy(tmp_path: Path) -> AgentAccessPolicy:
    """照 test_agent_access_policy.py 的 ``_make_policy`` 构造真 policy 与项目布局。"""
    project_root = (tmp_path / "repo").resolve()
    project_root.mkdir()
    policy = AgentAccessPolicy(
        project_root=project_root,
        data_root=project_root / "projects",
        agent_profile_root=(tmp_path / "agent_runtime_profile").resolve(),
    )
    (_projects_dir(policy) / "selfproj").mkdir(parents=True)
    (_projects_dir(policy) / "other").mkdir()
    (project_root / "lib").mkdir()
    (project_root / ".env").write_text("SECRET_TOKEN=1\nneedle\n", encoding="utf-8")
    return policy


@pytest.fixture
def project_cwd(access_policy: AgentAccessPolicy) -> Path:
    return _projects_dir(access_policy) / "selfproj"


@pytest.fixture
def file_tools(access_policy: AgentAccessPolicy, project_cwd: Path) -> CodexFileTools:
    return CodexFileTools(policy=access_policy, project_cwd=project_cwd, user_id=_USER_ID)


# ============================================================
# 未知工具与参数校验
# ============================================================


async def test_unknown_tool_reports_not_found(file_tools: CodexFileTools) -> None:
    result = await file_tools.call("NoSuchFileTool", {})

    assert result["success"] is False
    assert "not found" in _text(result).lower()


@pytest.mark.parametrize(
    ("tool", "arguments", "param"),
    [
        ("Read", {}, "file_path"),
        ("Write", {"file_path": "a.txt"}, "content"),
        ("Edit", {"file_path": "a.txt", "new_string": "x"}, "old_string"),
        ("Glob", {}, "pattern"),
        ("Grep", {}, "pattern"),
    ],
)
async def test_missing_required_argument_fails(
    file_tools: CodexFileTools, tool: str, arguments: dict[str, object], param: str
) -> None:
    result = await file_tools.call(tool, arguments)

    assert result["success"] is False
    assert param in _text(result)


@pytest.mark.parametrize(
    ("tool", "arguments", "param"),
    [
        ("Read", {"file_path": 123}, "file_path"),
        ("Write", {"file_path": "a.txt", "content": 123}, "content"),
        ("Edit", {"file_path": "a.txt", "old_string": 1, "new_string": "x"}, "old_string"),
        ("Glob", {"pattern": 123}, "pattern"),
        ("Grep", {"pattern": 123}, "pattern"),
    ],
)
async def test_wrong_argument_type_fails_without_raising(
    file_tools: CodexFileTools, tool: str, arguments: dict[str, object], param: str
) -> None:
    result = await file_tools.call(tool, arguments)

    assert result["success"] is False
    assert param in _text(result)


# ============================================================
# Read
# ============================================================


async def test_read_numbers_lines_from_one(file_tools: CodexFileTools, project_cwd: Path) -> None:
    await asyncio.to_thread(_write_text, project_cwd / "notes.txt", "alpha\nbeta\ngamma\n")

    result = await file_tools.call("Read", {"file_path": "notes.txt"})
    text = _text(result)

    assert result["success"] is True
    assert "1\talpha" in text
    assert "2\tbeta" in text
    assert "3\tgamma" in text


async def test_read_applies_offset_and_limit(file_tools: CodexFileTools, project_cwd: Path) -> None:
    await asyncio.to_thread(_write_text, project_cwd / "notes.txt", "one\ntwo\nthree\nfour\n")

    result = await file_tools.call("Read", {"file_path": "notes.txt", "offset": 2, "limit": 2})
    text = _text(result)

    assert result["success"] is True
    assert "2\ttwo" in text
    assert "3\tthree" in text
    assert "1\tone" not in text
    assert "four" not in text


async def test_read_defaults_to_read_default_limit(file_tools: CodexFileTools, project_cwd: Path) -> None:
    content = "".join(f"line-{index}\n" for index in range(1, READ_DEFAULT_LIMIT + 6))
    await asyncio.to_thread(_write_text, project_cwd / "long.txt", content)

    result = await file_tools.call("Read", {"file_path": "long.txt"})
    text = _text(result)

    assert result["success"] is True
    assert len(text.splitlines()) == READ_DEFAULT_LIMIT
    assert f"{READ_DEFAULT_LIMIT}\tline-{READ_DEFAULT_LIMIT}" in text
    assert f"{READ_DEFAULT_LIMIT + 1}\t" not in text


async def test_read_truncates_overlong_lines(file_tools: CodexFileTools, project_cwd: Path) -> None:
    line = "a" * (READ_MAX_LINE_CHARS * 3) + "TAIL_MARKER"
    await asyncio.to_thread(_write_text, project_cwd / "wide.txt", line + "\n")

    result = await file_tools.call("Read", {"file_path": "wide.txt"})
    text = _text(result)
    body = text.split("\t", 1)[1] if "\t" in text else ""

    assert result["success"] is True
    assert "TAIL_MARKER" not in text
    assert len(body) <= READ_MAX_LINE_CHARS + 3


async def test_read_missing_file_fails(file_tools: CodexFileTools) -> None:
    result = await file_tools.call("Read", {"file_path": "missing.txt"})

    assert result["success"] is False
    assert re.search(r"not found|找不到|不存在|没有", _text(result), re.IGNORECASE)


async def test_read_non_utf8_file_fails(file_tools: CodexFileTools, project_cwd: Path) -> None:
    await asyncio.to_thread(_write_bytes, project_cwd / "blob.bin", b"\xff\xfe\x00\x10\x11")

    result = await file_tools.call("Read", {"file_path": "blob.bin"})

    assert result["success"] is False
    assert re.search(r"utf-?8|编码|二进制|binary|decode", _text(result), re.IGNORECASE)


async def test_relative_path_resolves_against_project_cwd(file_tools: CodexFileTools, project_cwd: Path) -> None:
    await asyncio.to_thread(_write_text, project_cwd / "sub" / "nested.txt", "relative\n")

    result = await file_tools.call("Read", {"file_path": "sub/nested.txt"})

    assert result["success"] is True
    assert "relative" in _text(result)


# ============================================================
# Write
# ============================================================


async def test_write_creates_parent_directories(file_tools: CodexFileTools, project_cwd: Path) -> None:
    target = project_cwd / "nested" / "deeper" / "out.txt"

    result = await file_tools.call("Write", {"file_path": "nested/deeper/out.txt", "content": "hello world"})

    assert result["success"] is True
    assert "11" in _text(result)
    assert await asyncio.to_thread(target.read_text, encoding="utf-8") == "hello world"


async def test_write_into_another_project_is_denied(
    file_tools: CodexFileTools, access_policy: AgentAccessPolicy, project_cwd: Path
) -> None:
    target = _projects_dir(access_policy) / "other" / "blocked.txt"
    allowed, _ = access_policy.check_path_access("../other/blocked.txt", "Write", project_cwd, user_id=_USER_ID)

    assert not allowed

    result = await file_tools.call("Write", {"file_path": "../other/blocked.txt", "content": "nope"})

    assert result["success"] is False
    assert _text(result)
    assert not await asyncio.to_thread(target.exists)


async def test_write_to_sensitive_env_is_denied(
    file_tools: CodexFileTools, access_policy: AgentAccessPolicy, project_cwd: Path
) -> None:
    env_path = access_policy.project_root / ".env"
    before = await asyncio.to_thread(env_path.read_text, encoding="utf-8")
    allowed, _ = access_policy.check_path_access(str(env_path), "Write", project_cwd, user_id=_USER_ID)

    assert not allowed

    result = await file_tools.call("Write", {"file_path": str(env_path), "content": "HACKED=1\n"})

    assert result["success"] is False
    assert await asyncio.to_thread(env_path.read_text, encoding="utf-8") == before


# ============================================================
# Read 被拒的位置
# ============================================================


async def test_read_sensitive_file_is_denied(
    file_tools: CodexFileTools, access_policy: AgentAccessPolicy, project_cwd: Path
) -> None:
    env_path = access_policy.project_root / ".env"
    allowed, reason = access_policy.check_path_access(str(env_path), "Read", project_cwd, user_id=_USER_ID)

    assert not allowed
    assert reason

    result = await file_tools.call("Read", {"file_path": str(env_path)})

    assert result["success"] is False
    assert "SECRET_TOKEN" not in _text(result)


async def test_read_another_project_file_is_denied(
    file_tools: CodexFileTools, access_policy: AgentAccessPolicy, project_cwd: Path
) -> None:
    other_file = _projects_dir(access_policy) / "other" / "secret.txt"
    await asyncio.to_thread(_write_text, other_file, "other project data\n")
    allowed, reason = access_policy.check_path_access(str(other_file), "Read", project_cwd, user_id=_USER_ID)

    assert not allowed
    assert reason

    result = await file_tools.call("Read", {"file_path": str(other_file)})

    assert result["success"] is False
    assert "other project data" not in _text(result)


# ============================================================
# Edit
# ============================================================


async def test_edit_replaces_single_occurrence(file_tools: CodexFileTools, project_cwd: Path) -> None:
    target = project_cwd / "draft.md"
    await asyncio.to_thread(_write_text, target, "hello world\n")

    result = await file_tools.call("Edit", {"file_path": "draft.md", "old_string": "world", "new_string": "there"})

    assert result["success"] is True
    assert "1" in _text(result)
    assert await asyncio.to_thread(target.read_text, encoding="utf-8") == "hello there\n"


async def test_edit_missing_old_string_fails(file_tools: CodexFileTools, project_cwd: Path) -> None:
    await asyncio.to_thread(_write_text, project_cwd / "draft.md", "hello world\n")

    result = await file_tools.call("Edit", {"file_path": "draft.md", "old_string": "absent", "new_string": "there"})

    assert result["success"] is False
    assert re.search(r"old_string|不存在|not found|未找到", _text(result), re.IGNORECASE)


async def test_edit_multiple_occurrences_without_replace_all_fails(
    file_tools: CodexFileTools, project_cwd: Path
) -> None:
    target = project_cwd / "draft.md"
    await asyncio.to_thread(_write_text, target, "a a a\n")

    result = await file_tools.call("Edit", {"file_path": "draft.md", "old_string": "a", "new_string": "b"})

    assert result["success"] is False
    assert "3" in _text(result)
    assert await asyncio.to_thread(target.read_text, encoding="utf-8") == "a a a\n"


async def test_edit_replace_all_replaces_every_occurrence(file_tools: CodexFileTools, project_cwd: Path) -> None:
    target = project_cwd / "draft.md"
    await asyncio.to_thread(_write_text, target, "a a a\n")

    result = await file_tools.call(
        "Edit", {"file_path": "draft.md", "old_string": "a", "new_string": "b", "replace_all": True}
    )

    assert result["success"] is True
    assert "3" in _text(result)
    assert await asyncio.to_thread(target.read_text, encoding="utf-8") == "b b b\n"


async def test_edit_identical_old_and_new_string_fails(file_tools: CodexFileTools, project_cwd: Path) -> None:
    await asyncio.to_thread(_write_text, project_cwd / "draft.md", "hello\n")

    result = await file_tools.call("Edit", {"file_path": "draft.md", "old_string": "hello", "new_string": "hello"})

    assert result["success"] is False
    assert _text(result)


async def test_edit_missing_file_fails(file_tools: CodexFileTools) -> None:
    result = await file_tools.call("Edit", {"file_path": "missing.md", "old_string": "a", "new_string": "b"})

    assert result["success"] is False
    assert _text(result)


# ============================================================
# Glob
# ============================================================


async def test_glob_returns_paths_relative_to_project(file_tools: CodexFileTools, project_cwd: Path) -> None:
    await asyncio.to_thread(_write_text, project_cwd / "a.txt", "a")
    await asyncio.to_thread(_write_text, project_cwd / "sub" / "b.txt", "b")
    await asyncio.to_thread(_write_text, project_cwd / "sub" / "c.md", "c")

    result = await file_tools.call("Glob", {"pattern": "**/*.txt"})

    assert result["success"] is True
    assert set(_text(result).splitlines()) == {"a.txt", "sub/b.txt"}


async def test_glob_sorts_newest_first(file_tools: CodexFileTools, project_cwd: Path) -> None:
    older = project_cwd / "older.txt"
    newer = project_cwd / "newer.txt"
    await asyncio.to_thread(_write_text, older, "old")
    await asyncio.to_thread(_write_text, newer, "new")
    await asyncio.to_thread(os.utime, older, (1_000_000, 1_000_000))
    await asyncio.to_thread(os.utime, newer, (2_000_000, 2_000_000))

    result = await file_tools.call("Glob", {"pattern": "*.txt"})

    assert result["success"] is True
    assert _text(result).splitlines() == ["newer.txt", "older.txt"]


async def test_glob_without_matches_succeeds(file_tools: CodexFileTools) -> None:
    result = await file_tools.call("Glob", {"pattern": "**/*.nomatch"})

    assert result["success"] is True
    assert re.search(r"没有|未|no |not found|0", _text(result), re.IGNORECASE)


async def test_glob_caps_results(file_tools: CodexFileTools, project_cwd: Path) -> None:
    await asyncio.to_thread(_write_numbered_files, project_cwd / "many", SEARCH_MAX_RESULTS + 3)

    result = await file_tools.call("Glob", {"pattern": "many/*.txt"})

    assert result["success"] is True
    assert len(_text(result).splitlines()) == SEARCH_MAX_RESULTS


async def test_glob_skips_files_denied_by_policy(
    file_tools: CodexFileTools, access_policy: AgentAccessPolicy, project_cwd: Path
) -> None:
    env_path = access_policy.project_root / ".env"
    await asyncio.to_thread(_write_text, project_cwd / "visible.env", "LOCAL=1\n")
    leaked = project_cwd / "leaked.env"
    await asyncio.to_thread(leaked.symlink_to, env_path)
    allowed, _ = access_policy.check_path_access(str(leaked), "Glob", project_cwd, user_id=_USER_ID)

    assert not allowed

    result = await file_tools.call("Glob", {"pattern": "*.env"})
    text = _text(result)

    assert result["success"] is True
    assert "visible.env" in text
    assert "leaked.env" not in text


# ============================================================
# Grep
# ============================================================


async def test_grep_reports_file_line_and_content(file_tools: CodexFileTools, project_cwd: Path) -> None:
    await asyncio.to_thread(_write_text, project_cwd / "docs" / "a.txt", "first\nneedle here\n")

    result = await file_tools.call("Grep", {"pattern": "needle"})

    assert result["success"] is True
    assert "docs/a.txt:2:needle here" in _text(result)


async def test_grep_filters_by_glob(file_tools: CodexFileTools, project_cwd: Path) -> None:
    await asyncio.to_thread(_write_text, project_cwd / "a.py", "needle\n")
    await asyncio.to_thread(_write_text, project_cwd / "b.md", "needle\n")

    result = await file_tools.call("Grep", {"pattern": "needle", "glob": "*.md"})
    text = _text(result)

    assert result["success"] is True
    assert "b.md" in text
    assert "a.py" not in text


async def test_grep_invalid_regex_fails(file_tools: CodexFileTools) -> None:
    result = await file_tools.call("Grep", {"pattern": "("})

    assert result["success"] is False
    assert re.search(r"正则|regex|invalid|无效|错误", _text(result), re.IGNORECASE)


async def test_grep_searches_only_given_file(file_tools: CodexFileTools, project_cwd: Path) -> None:
    await asyncio.to_thread(_write_text, project_cwd / "a.txt", "needle in a\n")
    await asyncio.to_thread(_write_text, project_cwd / "b.txt", "needle in b\n")

    result = await file_tools.call("Grep", {"pattern": "needle", "path": "a.txt"})
    text = _text(result)

    assert result["success"] is True
    assert "a.txt" in text
    assert "b.txt" not in text


async def test_grep_skips_files_denied_by_policy(
    file_tools: CodexFileTools, access_policy: AgentAccessPolicy, project_cwd: Path
) -> None:
    env_path = access_policy.project_root / ".env"
    await asyncio.to_thread(_write_text, env_path, "SECRET_TOKEN=1\nneedle in env\n")
    leaked = project_cwd / "leaked.env"
    await asyncio.to_thread(leaked.symlink_to, env_path)
    await asyncio.to_thread(_write_text, project_cwd / "notes.txt", "needle here\n")
    allowed, _ = access_policy.check_path_access(str(leaked), "Grep", project_cwd, user_id=_USER_ID)

    assert not allowed

    result = await file_tools.call("Grep", {"pattern": "needle"})
    text = _text(result)

    assert result["success"] is True
    assert "notes.txt" in text
    assert "leaked.env" not in text
    assert "needle in env" not in text
