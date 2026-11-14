"""Strict parsing for the persisted project schema discriminator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

CURRENT_PROJECT_SCHEMA_VERSION = 20
#: 迁移链能接的最早版本（ADR 0131）：更早的项目（含缺 ``schema_version`` 读作的 v0）被拒，
#: 需先在上游 ArcReel 里打开、升级到此版本或更高再导出。
MINIMUM_PROJECT_SCHEMA_VERSION = 19


def parse_project_schema_version(project: Mapping[str, object]) -> int:
    """Return a canonical non-negative version without coercing corrupt data."""

    raw_version = project.get("schema_version")
    if raw_version is None:
        return 0
    if type(raw_version) is not int or raw_version < 0:
        raise ValueError(f"schema_version must be an integer, got {raw_version!r}")
    return raw_version


def read_project_schema_version(project_dir: Path) -> int | None:
    """Read the schema version from ``project_dir/project.json``, or ``None`` when it cannot be read.

    A directory without a parseable ``project.json`` is not a project anyone can rule on by version;
    whoever resolved the name owns that verdict.
    """

    try:
        data = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, ValueError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return parse_project_schema_version(data)
    except ValueError:
        return None


def project_schema_below_minimum(project_dir: Path) -> bool:
    """Whether the project reads as older than the oldest schema the migration chain accepts."""

    version = read_project_schema_version(project_dir)
    return version is not None and version < MINIMUM_PROJECT_SCHEMA_VERSION


def project_schema_is_current(project: Mapping[str, object]) -> bool:
    """Return whether a strictly parsed project uses the current schema."""

    version = parse_project_schema_version(project)
    if version > CURRENT_PROJECT_SCHEMA_VERSION:
        raise ValueError(f"schema_version {version} is newer than supported version {CURRENT_PROJECT_SCHEMA_VERSION}")
    return version == CURRENT_PROJECT_SCHEMA_VERSION


__all__ = [
    "CURRENT_PROJECT_SCHEMA_VERSION",
    "MINIMUM_PROJECT_SCHEMA_VERSION",
    "parse_project_schema_version",
    "project_schema_below_minimum",
    "project_schema_is_current",
    "read_project_schema_version",
]
