"""恢复回来的项目走启动时的迁移链；版本早于最低版本的项目，源文件编码迁移与 schema 迁移都不碰它。"""

from __future__ import annotations

import json
from pathlib import Path

from lib.infra.data_root_layout import DataRootLayout
from lib.project import deleted_projects
from lib.project.project_migration_failure import SCHEMA_UNSUPPORTED_CODE, load_migration_failure


def test_restoring_a_project_older_than_the_minimum_schema_leaves_its_files_untouched(tmp_path: Path) -> None:
    project_dir = DataRootLayout(tmp_path / "data").projects_dir / "old"
    (project_dir / "source").mkdir(parents=True)
    (project_dir / "project.json").write_text(json.dumps({"schema_version": 18, "name": "old"}), encoding="utf-8")
    (project_dir / "source" / "novel.txt").write_bytes("春天来了".encode("gbk"))
    before = {path: path.read_bytes() for path in project_dir.rglob("*") if path.is_file()}

    deleted_projects.migrate_restored(project_dir)

    assert {path: path.read_bytes() for path in before} == before
    assert not (project_dir / ".arcreel").exists()
    failure = load_migration_failure(project_dir)
    assert failure is not None
    assert failure.code == SCHEMA_UNSUPPORTED_CODE
