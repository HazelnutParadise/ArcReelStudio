"""早于迁移链最早版本的项目：裁决、制作状态、计划、生成入口与重试都报「版本过旧」，不报「修复后重试」。

断言的是外部可观察的输出：磁盘上的裁决记录、制作状态的 blocker 与下一步、计划的单条 problem、
项目摘要、生成入口的拒绝与重试工具的返回。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.generation.generation_result import GenerationAction, GenerationProblemCode
from lib.infra.api_errors import ConflictError
from lib.project.project_manager import ProjectManager
from lib.project.project_migration_failure import (
    MIGRATION_FAILURE_CODE,
    MIGRATION_FAILURE_FILENAME,
    SCHEMA_UNSUPPORTED_CODE,
    UPGRADE_UPSTREAM_ACTION,
    load_migration_failure,
)
from lib.project.project_migrations.runner import run_project_migrations
from lib.project.project_schema import MINIMUM_PROJECT_SCHEMA_VERSION
from lib.workflow.workflow_plan import WorkflowPlanRequest
from lib.workflow.workflow_state import WorkflowStateService
from server.services.project.workflow_planner import WorkflowPlanner
from tests.fakes import use_project_manager
from tests.legacy_project_shapes import write_v19_project

_OLD_VERSION = MINIMUM_PROJECT_SCHEMA_VERSION - 1
_PARAMS = {"version": _OLD_VERSION, "minimum": MINIMUM_PROJECT_SCHEMA_VERSION}


def _refused_project(tmp_path: Path) -> Path:
    """一个 schema 早于最低版本的项目，已经过一次启动期迁移、被拒并记下裁决。"""

    projects_root = tmp_path / "projects"
    project_dir = write_v19_project(projects_root, activate=False)
    project_path = project_dir / "project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    project["schema_version"] = _OLD_VERSION
    project_path.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
    assert run_project_migrations(projects_root).failed == ["demo"]
    return project_dir


def test_the_recorded_verdict_names_the_version_and_the_minimum(tmp_path: Path) -> None:
    project_dir = _refused_project(tmp_path)

    failure = load_migration_failure(project_dir)

    assert failure is not None
    assert failure.code == SCHEMA_UNSUPPORTED_CODE
    assert failure.params == _PARAMS
    assert failure.failed_at


def test_a_verdict_stored_before_the_code_existed_still_reads_as_a_migration_failure(tmp_path: Path) -> None:
    project_dir = write_v19_project(tmp_path / "projects", activate=False)
    (project_dir / MIGRATION_FAILURE_FILENAME).write_text(
        json.dumps({"schema_version": 19, "failed_at": "2026-11-01T00:00:00", "reason": "boom", "details": []}),
        encoding="utf-8",
    )

    failure = load_migration_failure(project_dir)

    assert failure is not None
    assert failure.code == MIGRATION_FAILURE_CODE
    assert failure.params == {}
    assert failure.reason == "boom"


def test_workflow_status_blocks_with_the_schema_code_and_points_upstream(tmp_path: Path) -> None:
    _refused_project(tmp_path)

    status = WorkflowStateService(ProjectManager(str(tmp_path))).get_status("demo")

    assert [blocker.code for blocker in status.blockers] == [SCHEMA_UNSUPPORTED_CODE]
    assert status.next_action.type == UPGRADE_UPSTREAM_ACTION
    assert status.next_action.args == _PARAMS


async def test_workflow_plan_reports_one_problem_with_no_retry(tmp_path: Path) -> None:
    _refused_project(tmp_path)

    plan = await WorkflowPlanner(ProjectManager(str(tmp_path))).get_plan("demo", WorkflowPlanRequest())

    [problem] = plan.problems
    assert problem.code == GenerationProblemCode.PROJECT_SCHEMA_UNSUPPORTED
    assert problem.action == GenerationAction.UPGRADE_PROJECT_UPSTREAM
    assert problem.params is not None
    assert {key: problem.params[key] for key in _PARAMS} == _PARAMS
    assert plan.next_action.type == UPGRADE_UPSTREAM_ACTION


def test_project_summary_carries_the_schema_code(tmp_path: Path) -> None:
    _refused_project(tmp_path)

    summary = WorkflowStateService(ProjectManager(str(tmp_path))).get_project_summary("demo")

    assert summary.needs_repair is True
    assert summary.repair_code == SCHEMA_UNSUPPORTED_CODE


def test_generation_entries_refuse_with_the_schema_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import lib.project.project_migration_guard as guard

    _refused_project(tmp_path)
    use_project_manager(monkeypatch, ProjectManager(str(tmp_path)))

    with pytest.raises(ConflictError) as excinfo:
        guard.assert_project_migration_ok("demo")

    assert excinfo.value.key == SCHEMA_UNSUPPORTED_CODE
    assert {key: excinfo.value.params[key] for key in _PARAMS} == _PARAMS


def test_a_project_short_of_the_minimum_without_a_record_still_reads_as_unsupported(tmp_path: Path) -> None:
    """启动期之后才落进来的旧项目还没有裁决记录：按版本判定的待定裁决同样报「版本过旧」。"""

    project_dir = _refused_project(tmp_path)
    (project_dir / MIGRATION_FAILURE_FILENAME).unlink()

    status = WorkflowStateService(ProjectManager(str(tmp_path))).get_status("demo")

    assert [blocker.code for blocker in status.blockers] == [SCHEMA_UNSUPPORTED_CODE]
    assert status.next_action.args == _PARAMS


async def test_the_retry_tool_returns_the_schema_problem_without_touching_the_project(tmp_path: Path) -> None:
    from server.agent_toolset.repair_channel import RETRY_PROJECT_MIGRATION
    from tests.integration.server.agent_tool_support import ToolHarness, run_declared_tool

    project_dir = _refused_project(tmp_path)
    project_json = (project_dir / "project.json").read_bytes()
    ctx = ToolHarness(project_name="demo", data_root=tmp_path, pm=ProjectManager(str(tmp_path)))

    outcome = await run_declared_tool(RETRY_PROJECT_MIGRATION, ctx, {})

    assert outcome.problem is not None
    assert outcome.problem.code == SCHEMA_UNSUPPORTED_CODE
    assert outcome.problem.action == UPGRADE_UPSTREAM_ACTION
    assert (project_dir / "project.json").read_bytes() == project_json
