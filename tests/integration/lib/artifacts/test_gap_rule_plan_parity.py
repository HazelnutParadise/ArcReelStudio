"""缺口规则借用 v17、v18 选口径：对输入完整的当前 schema 项目，两种口径与常规规划的依据摘要逐条相同。

导入激活靠这两次规划的差集补录因缺口跳过的产物；借来的版本号若让依据按旧口径投影（不记风格描述、
记资产名等），补录的条目就会与常规规划的登记不一致。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.artifacts.artifact_activation import plan_artifact_target_state
from lib.artifacts.artifact_planner import plan_artifact_target_state_by_gap_rule
from tests.integration.lib.artifacts.test_planner_basis_digest_guard import _grid_storyboard_project


@pytest.mark.parametrize("record_gaps", [False, True], ids=["gaps-refused", "gaps-recorded"])
def test_the_gap_rule_plans_the_same_bases_as_the_regular_plan(tmp_path: Path, record_gaps: bool) -> None:
    project_dir = _grid_storyboard_project(tmp_path)
    project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))

    regular = plan_artifact_target_state(project_dir).entries
    by_gap_rule = plan_artifact_target_state_by_gap_rule(project_dir, project, record_gaps=record_gaps).entries

    assert {key.kind.value for key in regular} >= {"asset-sheet", "episode-grid", "episode-storyboard"}
    assert {key: (entry.artifact_path, entry.basis_digest) for key, entry in by_gap_rule.items()} == {
        key: (entry.artifact_path, entry.basis_digest) for key, entry in regular.items()
    }
