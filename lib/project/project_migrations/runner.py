"""Runner: 扫描 projects/ 并按版本顺序跑迁移器。"""

from __future__ import annotations

import json
import logging
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from lib.episode.episode_ledger import parse_positive_episode_num
from lib.episode.episode_paths import episode_drafts_dir
from lib.infra.data_root_layout import DataRootLayout, list_project_dirs
from lib.infra.path_safety import try_safe_join
from lib.project.project_migration_failure import (
    MigrationFailureRecord,
    ProjectMigrationError,
    clear_migration_failure,
    record_migration_failure,
)
from lib.project.project_migration_report import (
    ArtifactBackfillOutcome,
    MigrationAdjustment,
    build_migration_report,
    complete_migration_report,
    load_migration_report,
    write_migration_report,
)
from lib.project.project_migrations.backups import ensure_versioned_backup, versioned_backup_candidates
from lib.project.project_migrations.legacy_shapes import normalize_legacy_shapes
from lib.project.project_migrations.v19_to_v20_bare_provider_models import (
    ExcludedRecommendations,
    migrate_v19_to_v20,
)
from lib.project.project_schema import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    MINIMUM_PROJECT_SCHEMA_VERSION,
    parse_project_schema_version,
)

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = CURRENT_PROJECT_SCHEMA_VERSION

#: 链首规整可能在草稿目录里落备份的脚本规划与提示词编写草稿文件名（当前落盘名）；回收侧按它们枚举。
_DRAFT_BACKUP_NAMES: tuple[str, ...] = (
    "script_plan_normalized_script.json",
    "script_plan_normalized_script.invalid.json",
    "script_plan_normalized_script.md",
    "script_plan_segments.json",
    "script_plan_segments.invalid.json",
    "script_plan_segments.md",
    "script_plan_reference_units.json",
    "script_plan_reference_units.invalid.json",
    "script_plan_reference_units.md",
    "prompt_authoring_reference_script.invalid.json",
)

#: 迁移器返回值：改写产物清单的步返回本步登记与跳过的产物，runner 把链上最后一份折进迁移报告。
MIGRATORS: dict[int, Callable[..., ArtifactBackfillOutcome | None]] = {}


def _bound_script_sources(project_dir: Path) -> tuple[Path, ...]:
    """Resolve every script-shaped source a migration was allowed to back up.

    账本里绑定的剧集脚本，加上同集的 script_plan 草稿——草稿是同一份正文的上一形态，改写脚本的
    迁移同批改写它，备份因此成对出现，回收也必须成对，否则草稿备份没有任何清理路径。
    """

    try:
        project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, ValueError:
        return ()
    episodes = project.get("episodes") if isinstance(project, dict) else None
    if not isinstance(episodes, list):
        return ()
    sources: list[Path] = []
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        script_file = episode.get("script_file")
        if isinstance(script_file, str) and script_file:
            source = try_safe_join(project_dir, script_file)
            if source is not None:
                sources.append(source)
        episode_num = parse_positive_episode_num(episode.get("episode"))
        if episode_num is not None:
            drafts_dir = episode_drafts_dir(project_dir, episode_num)
            sources.extend(drafts_dir / name for name in _DRAFT_BACKUP_NAMES)
    return tuple(sources)


@dataclass
class MigrationSummary:
    migrated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def _load_schema_version(project_dir: Path) -> int:
    pj = project_dir / "project.json"
    if not pj.exists():
        return -1  # 跳过非项目目录
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("project.json 必须包含对象")
        return parse_project_schema_version(data)
    except Exception as exc:
        logger.warning("project.json 损坏或 schema_version 不可解析，跳过：%s（%s）", project_dir, exc)
        return -1


def _backup_project_json(project_dir: Path, from_version: int) -> None:
    """同一起点版本、内容相同的 ``project.json`` 只留一份备份。"""

    ensure_versioned_backup(project_dir / "project.json", from_version)


def _refuse_unsupported_version(version: int) -> None:
    """早于迁移链最早版本的项目在规整与任何备份之前就拒绝，项目目录一个字节都不动。"""

    if version < MINIMUM_PROJECT_SCHEMA_VERSION:
        raise ProjectMigrationError(
            f"schema version {version} is older than v{MINIMUM_PROJECT_SCHEMA_VERSION}, the oldest version this "
            f"migration chain accepts; open the project in upstream ArcReel to upgrade it to "
            f"v{MINIMUM_PROJECT_SCHEMA_VERSION} or later, then export it again",
            file="project.json",
        )


def migrate_project_dir(
    project_dir: Path,
    *,
    excluded_recommendations: ExcludedRecommendations | None = None,
) -> bool:
    """将单个项目目录逐级升级到 CURRENT_SCHEMA_VERSION，返回是否实际迁移。

    供启动期 ``run_project_migrations`` 与项目导入路径共用：启动期 runner 只覆盖启动时已存在的
    项目，启动后导入的旧归档需在导入入口补跑此函数走完整迁移链，否则解析链（不再读 legacy
    字段）会让该项目静默回退到全局默认。非项目目录 / 已是最新版本返回 False；早于
    ``MINIMUM_PROJECT_SCHEMA_VERSION`` 的项目抛 :class:`ProjectMigrationError`，目录不动。

    ``excluded_recommendations`` 转交 v19→v20：这些推荐模型不写进项目
    （归档导入传入用户停用的模型），缺省时直接用目录的推荐。"""
    version = _load_schema_version(project_dir)
    if version < 0:
        return False
    if version >= CURRENT_SCHEMA_VERSION:
        _finish_unfinished_report(project_dir)
        return False
    _refuse_unsupported_version(version)
    start_version = version
    outcome: ArtifactBackfillOutcome | None = None
    # 上一次没走完的链规整过的旧形态已经落盘，这一次规整不会再发现它们：从未完成的报告里接着记。
    carried = load_migration_report(project_dir)
    if carried is not None and not carried.complete:
        start_version = min(start_version, carried.from_schema_version)
        adjusted: list[MigrationAdjustment] = list(carried.adjusted)
    else:
        adjusted = []
    try:
        # 链首规整：v19 起的数据仍可能带着旧版正常流程写出的形态（ADR 0098）。
        normalize_legacy_shapes(project_dir, schema_version=version, record=adjusted)
        while version < CURRENT_SCHEMA_VERSION:
            _backup_project_json(project_dir, version)
            migrator = MIGRATORS.get(version)
            if not migrator:
                raise RuntimeError(f"no migrator from v{version}")
            if migrator is migrate_v19_to_v20:
                step_outcome = migrate_v19_to_v20(project_dir, excluded=excluded_recommendations)
            else:
                step_outcome = migrator(project_dir)
            if step_outcome is not None:
                outcome = step_outcome
            version += 1
        if outcome is not None or adjusted:
            # 链上最后一次清单改写描述的是迁移完成时清单的全貌，报告只留这一份。
            write_migration_report(
                project_dir,
                build_migration_report(
                    outcome,
                    from_schema_version=start_version,
                    to_schema_version=CURRENT_SCHEMA_VERSION,
                    adjusted=adjusted,
                ),
            )
    except BaseException:
        # 收尾那次写报告失败、或最后一步提交了当前版本之后才失败，同样留下未完成的报告：
        # 下次启动看到项目已在当前版本，由 ``_finish_unfinished_report`` 补写成完成的报告。
        # 链已走完时 ``outcome`` 就是清单的全貌，跳过项随报告留下；中途失败时重试会重新算出它们。
        finished = outcome if version >= CURRENT_SCHEMA_VERSION else None
        if adjusted or finished is not None:
            _record_unfinished_report(project_dir, finished, adjusted, from_version=start_version, to_version=version)
        raise
    return True


def _finish_unfinished_report(project_dir: Path) -> None:
    """项目已在当前版本、报告却仍未完成时补写成完成的报告；写不下只记日志，下次启动再补。

    链在提交当前版本之后才失败（最后一步提交后报错，或收尾那次写报告失败）时，重跑不会再进链，
    未完成的报告不补写就永远不对用户显示。
    """

    try:
        complete_migration_report(project_dir, to_schema_version=CURRENT_SCHEMA_VERSION)
    except OSError as exc:
        logger.warning("无法补写未完成的迁移报告：%s（%s）", project_dir, exc)


def _record_unfinished_report(
    project_dir: Path,
    outcome: ArtifactBackfillOutcome | None,
    adjusted: list[MigrationAdjustment],
    *,
    from_version: int,
    to_version: int,
) -> None:
    """链失败时留下已落盘的规整记录（链已走完时连同清单结果）；写不下只记日志，不盖过链本身的失败。"""

    try:
        write_migration_report(
            project_dir,
            build_migration_report(
                outcome,
                from_schema_version=from_version,
                to_schema_version=to_version,
                adjusted=adjusted,
                complete=False,
            ),
        )
    except OSError as exc:
        logger.warning("无法记下未完成迁移的规整记录：%s（%s）", project_dir, exc)


def _append_error_log(project_dir: Path, tb: str) -> None:
    """Keep the full traceback out of the user-facing verdict but on disk for support."""

    error_log = DataRootLayout.for_project_dir(project_dir).project_migration_error_log_path
    try:
        error_log.parent.mkdir(parents=True, exist_ok=True)
        with error_log.open("a", encoding="utf-8") as handle:
            handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {project_dir.name}\n{tb}\n")
    except OSError as exc:
        logger.warning("无法写入迁移错误日志：%s（%s）", error_log, exc)


def migrate_project_with_verdict(project_dir: Path) -> MigrationFailureRecord | None:
    """Run the chain for one project and persist the verdict beside its data.

    Returns ``None`` once the project sits at the current schema — the previous
    verdict, if any, is cleared — or the recorded failure. Idempotent: a project
    that is already current is a no-op success, so retrying costs nothing.
    """

    try:
        migrate_project_dir(project_dir)
    except Exception as exc:  # 单个项目失败被隔离，不中断整体迁移
        logger.error("迁移失败 %s: %s", project_dir.name, exc)
        # The persisted verdict is what the production status, the production plan
        # and every generation entry read to refuse work on this project.
        _append_error_log(project_dir, traceback.format_exc())
        return record_migration_failure(project_dir, exc, schema_version=_load_schema_version(project_dir))
    version = _load_schema_version(project_dir)
    if version != CURRENT_SCHEMA_VERSION:
        # ``migrate_project_dir`` returns without raising for a directory it cannot
        # place on the chain at all — no readable ``project.json``, or a version the
        # chain does not cover. Reaching the current schema is the only evidence the
        # project is repaired, so anything else keeps it blocked.
        return record_migration_failure(
            project_dir,
            ProjectMigrationError(
                f"schema version {version} did not reach v{CURRENT_SCHEMA_VERSION}",
                file="project.json",
            ),
            schema_version=version,
        )
    # A retry that finally lands clears the verdict, so the project stops being
    # reported as blocked without any further user action.
    clear_migration_failure(project_dir)
    return None


def run_project_migrations(projects_dir: Path) -> MigrationSummary:
    """扫项目目录下每个项目，升级到 CURRENT_SCHEMA_VERSION。"""
    summary = MigrationSummary()
    if not projects_dir.exists():
        return summary

    for child in list_project_dirs(projects_dir):
        version = _load_schema_version(child)
        if version < 0:
            continue  # project.json 损坏
        # Persisting the verdict is itself disk work: one project whose directory
        # cannot be written must not abort the pass for every project after it.
        try:
            if version >= CURRENT_SCHEMA_VERSION:
                # A project that reached the current schema by any route is not blocked;
                # a verdict left over from an earlier attempt would strand it forever.
                clear_migration_failure(child)
                _finish_unfinished_report(child)
                summary.skipped.append(child.name)
                continue

            if migrate_project_with_verdict(child) is None:
                summary.migrated.append(child.name)
            else:
                summary.failed.append(child.name)
        except OSError as exc:
            logger.error("迁移裁决无法落盘 %s：%s", child.name, exc)
            summary.failed.append(child.name)

    return summary


def cleanup_stale_backups(projects_dir: Path, max_age_days: int = 7) -> None:
    """删除超过 max_age_days、且可归属到迁移输入的版本化备份。"""
    if not projects_dir.exists():
        return
    cutoff = time.time() - max_age_days * 86400
    for project_dir in list_project_dirs(projects_dir):
        # 每一步的输入备份留到那一步的版本提升坐实为止：项目仍停在 v<N> 时，``*.bak.v<N>-*``
        # 是那一步失败后唯一的恢复线索，只回收起点版本已低于当前 schema 的备份。起点早于
        # ``MINIMUM_PROJECT_SCHEMA_VERSION`` 的备份是旧版迁移链留下的，一并按期回收。
        schema_version = _load_schema_version(project_dir)
        project_backup_versions = tuple(
            version for version in range(CURRENT_SCHEMA_VERSION) if version < schema_version
        )
        sources = (
            (project_dir / "project.json", project_backup_versions),
            (project_dir / "versions" / "versions.json", project_backup_versions),
            # 链首规整改写资产图登记、衍生登记与剧本登记时备份清单。
            (project_dir / ".arcreel_artifacts.json", project_backup_versions),
            *((source, project_backup_versions) for source in _bound_script_sources(project_dir)),
        )
        for source, versions in sources:
            for bak in versioned_backup_candidates(source, versions):
                if bak.is_symlink() or not bak.is_file():
                    continue
                try:
                    if bak.stat().st_mtime < cutoff:
                        bak.unlink()  # hard-delete: infra -- 过期的迁移备份
                except OSError:
                    logger.warning("无法删除备份：%s", bak)


# 注册迁移器（顶部 import，此处仅赋值）
MIGRATORS[19] = migrate_v19_to_v20
