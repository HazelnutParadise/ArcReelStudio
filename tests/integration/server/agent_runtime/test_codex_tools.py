"""Codex 引擎的 ArcReel 工具：与内嵌 Claude server 同一份工具集与 schema，调用走同一套声明与会话项目 scope。"""

from __future__ import annotations

import json
from pathlib import Path

from lib.project.project_manager import ProjectManager
from server.agent_runtime.arcreel_mcp import build_arcreel_mcp_server
from server.agent_runtime.codex_tools import build_arcreel_codex_tools
from server.agent_toolset.toolset import AGENT_TOOLSET


def test_lists_every_tool_with_the_declared_schema(tmp_path: Path) -> None:
    tools = build_arcreel_codex_tools(project_name="demo", data_root=tmp_path)

    by_name = {spec["name"]: spec for spec in tools.specs}
    assert set(by_name) == {declaration.name for declaration in AGENT_TOOLSET}
    for declaration in AGENT_TOOLSET:
        spec = by_name[declaration.name]
        assert spec["type"] == "function"
        assert spec["inputSchema"] == declaration.input_schema
        assert spec["description"]


async def test_tool_specs_match_the_claude_engine(tmp_path: Path) -> None:
    from mcp.client import Client

    server = build_arcreel_mcp_server(project_name="demo", data_root=tmp_path)["instance"]
    async with Client(server) as client:
        listed = await client.list_tools()
    claude = {tool.name: (tool.description, tool.input_schema) for tool in listed.tools}
    codex = {
        spec["name"]: (spec["description"], spec["inputSchema"])
        for spec in build_arcreel_codex_tools(project_name="demo", data_root=tmp_path).specs
    }

    assert codex == claude


async def test_calls_run_in_the_session_project(tmp_path: Path) -> None:
    projects = ProjectManager(tmp_path / "projects")
    tools = build_arcreel_codex_tools(project_name="demo", data_root=projects.data_root)

    created = await tools.call("create_project", {"name": "demo", "title": "Demo"})
    listed = await tools.call("list_projects", {})
    uploaded = await tools.call("upload_source", {"filename": "novel.txt", "content": "hello"})

    assert [r["success"] for r in (created, listed, uploaded)] == [True, True, True]
    assert listed["contentItems"][-1]["type"] == "inputText"
    assert [p["name"] for p in json.loads(listed["contentItems"][-1]["text"])["projects"]] == ["demo"]
    assert (projects.get_project_path("demo") / "source" / "novel.txt").read_text(encoding="utf-8") == "hello"


async def test_unknown_tools_and_bad_arguments_fail_without_raising(tmp_path: Path) -> None:
    tools = build_arcreel_codex_tools(project_name="demo", data_root=tmp_path)

    unknown = await tools.call("does_not_exist", {})
    bad = await tools.call("create_project", {"name": 123})

    assert unknown["success"] is False
    assert "not found" in unknown["contentItems"][0]["text"]
    assert bad["success"] is False
