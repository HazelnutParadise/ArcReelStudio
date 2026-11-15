"""Eager Artifact Manifest target-state planning and activation.

The schema migration and archive-import boundary both call this module.  It is
the only place that reconstructs a complete manifest from canonical project
state; ordinary readers never repair or infer entries on first access.

规划、时新性判定、输入认领与注册各自独立成模块（``artifact_planner`` /
``artifact_currency`` / ``artifact_input_claims`` / ``artifact_registration``）；
本模块留下激活与提交编排，并作为四者对外的统一入口 re-export 全部公开符号。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast

from lib.artifacts.artifact_currency import (
    ArtifactComparer,
    ArtifactCurrencyResolver,
    RegisteredArtifactResolver,
    active_artifact_currency_resolver,
    artifact_is_usable,
    read_artifact_content_digest,
    resolve_artifact_episode,
    resolve_current_artifact_basis,
    resolve_current_artifact_target,
)
from lib.artifacts.artifact_input_claims import (
    EpisodeScriptInput,
    artifact_input_is_usable,
    assert_artifact_input_claims_usable,
    assert_current_artifact_input_claims_usable,
    bind_artifact_input_claims_to_content_digests,
    bind_artifact_input_claims_to_frozen_visuals,
    resolve_usable_artifact_input_claim,
    resolve_usable_episode_script_input,
    resolve_usable_storyboard_video_inputs,
    snapshot_usable_artifact_input_claim,
)
from lib.artifacts.artifact_manifest import (
    MANIFEST_FILENAME,
    ArtifactBasis,
    ArtifactBasisDescriptor,
    ArtifactContentFacts,
    ArtifactInputClaim,
    ArtifactKey,
    ArtifactKind,
    ArtifactManifestAdapter,
    ArtifactManifestArchiveSnapshot,
    ArtifactManifestEntry,
    ArtifactManifestError,
    ProjectArtifactManifestAdapter,
)
from lib.artifacts.artifact_planner import (
    ArtifactTargetStateChangedError,
    ArtifactTargetStatePlan,
    SharedVersionMetadata,
    TargetStatePlanner,
    episode_scope_for_key,
    gap_backfill_entries,
    plan_artifact_target_state,
    plan_artifact_target_state_by_gap_rule,
)
from lib.artifacts.artifact_registration import (
    artifact_key_for_resource,
    forget_current_resource_artifact,
    forget_unbound_grid_artifacts,
    forget_unbound_storyboard_artifacts,
    register_artifact_entries_atomically,
    register_current_artifact,
    register_current_artifact_if_provable,
    register_current_resource_artifact,
    register_task_current_resource_artifact,
    resolve_current_resource_artifact_basis,
)
from lib.artifacts.formal_write import project_metadata_lock
from lib.artifacts.visual_artifact_provenance import (
    visual_file_digest,
)
from lib.infra.content_digest import TextModeDigest
from lib.project.project_migration_report import MigrationSkippedArtifact, skipped_artifact_identity
from lib.project.project_schema import project_schema_is_current

_EPISODE_RESOURCE_KINDS = frozenset(
    {
        ArtifactKind.EPISODE_STORYBOARD,
        ArtifactKind.EPISODE_VIDEO,
        ArtifactKind.EPISODE_AUDIO,
        ArtifactKind.EPISODE_SUBTITLE,
        ArtifactKind.EPISODE_PRESENTATION,
    }
)


def activate_artifact_target_state(
    project_dir: Path,
    *,
    plan: ArtifactTargetStatePlan | None = None,
) -> bool:
    """Commit one complete target state for a current-schema project; the schema version is left as it is.

    ``plan`` 供调用方把只读预检提到自身写盘段之前完成；缺省即在此就地预检。传入的计划仍要
    过 ``assert_artifact_target_state_plan_unchanged``，它对着盘上事实自证，晚于预检的改动一律拒绝。
    """

    if plan is None:
        plan = plan_artifact_target_state(project_dir)
    if not project_schema_is_current(plan.project):
        raise ValueError("schema-preserving activation requires a current-schema project")

    assert_artifact_target_state_plan_unchanged(project_dir, plan)
    return ProjectArtifactManifestAdapter(project_dir).replace_entries_atomically(plan.entries)


def ensure_imported_artifact_target_state(
    project_dir: Path,
    *,
    preserved_manifest: ArtifactManifestArchiveSnapshot | None = None,
) -> tuple[MigrationSkippedArtifact, ...]:
    """Eagerly materialize the Artifact Manifest sidecar at the archive staging boundary.

    Official exports carry the complete source Manifest in their visible archive
    envelope.  Its basis digests are immutable generation evidence and its content
    digests bind those claims to the exported formal bytes.  Validate the claims
    against the imported canonical target plan, then commit one snapshot in which
    each claim is settled by its content evidence: an exact digest match restores
    the frozen claim; a digest that only matches the text-mode view (CRLF folded,
    cut at ``0x1A``) cannot prove the whole artifact, so that key is re-registered
    from the current self-proving projection instead; any other digest rejects the
    import.  Formal artifacts the envelope carries no claim for because generation-input
    gaps once blocked their projection are backfilled from the self-proving projection
    (``docs/adr/0098``: planned once refusing gaps and once recording them, only the keys the
    second plan adds are taken); other unclaimed
    artifacts stay unregistered.  Legacy archives without the envelope retain the
    self-proving path.

    返回规划器看见、但最终没有登记的产物及原因：导入不分 schema 版本都把它们列进迁移报告的
    「未能带入」（ADR 0098）。
    """

    raw = (project_dir / "project.json").read_bytes()
    try:
        project = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("project.json is not valid UTF-8 JSON") from exc
    if not isinstance(project, Mapping) or not project_schema_is_current(project):
        raise ValueError("archive activation requires a current-schema project")
    if preserved_manifest is not None:
        preserved_entries = dict(preserved_manifest.entries)
        preserved_content_digests = dict(preserved_manifest.content_digests)
        if set(preserved_entries) != set(preserved_content_digests):
            raise ValueError("archive Artifact Manifest content evidence does not cover every formal claim")
        with project_metadata_lock(project_dir):
            plan = _plan_preserved_artifact_target_state(project_dir)
            gaps_refused = plan_artifact_target_state_by_gap_rule(project_dir, project, record_gaps=False)
            gaps_recorded = plan_artifact_target_state_by_gap_rule(project_dir, project, record_gaps=True)
            rebased = _rebase_preserved_artifact_entries(plan, preserved_entries)
            invalid = [key.encode() for key, archived in preserved_entries.items() if rebased[key] != archived]
            if invalid:
                raise ValueError(f"archive Artifact Manifest contains unprovable formal claims: {sorted(invalid)}")
            assert_artifact_target_state_plan_unchanged(project_dir, plan)
            adapter = ProjectArtifactManifestAdapter(project_dir)
            restored: dict[ArtifactKey, ArtifactManifestEntry] = {}
            replaced: list[str] = []
            for key, entry in preserved_entries.items():
                evidence = _archived_content_evidence(adapter, entry.artifact_path, preserved_content_digests[key])
                if evidence == "exact":
                    # 视频与音频只在激活证明「正式文件 = 选中快照」成立、且证明的就是这份字节时带上内容事实；
                    # 证明不成立的条目不带事实，导入后照常判 stale，与源项目一致。
                    projected = plan.entries.get(key)
                    content = projected.content if projected is not None else None
                    restored[key] = (
                        replace(entry, content=content)
                        if content is not None and content.digest == preserved_content_digests[key]
                        else entry
                    )
                elif evidence == "text_mode":
                    # 文本模式摘要丢了字节，绑不住整份产物：这条 claim 按无信封归档的口径，
                    # 用当前投影自证补录；投影不出条目的目标不登记。
                    projected = plan.entries.get(key)
                    if projected is not None:
                        restored[key] = projected
                else:
                    replaced.append(key.encode())
            if replaced:
                raise ValueError(
                    f"archive Artifact Manifest formal artifact content does not match its claims: {sorted(replaced)}"
                )
            restored.update(gap_backfill_entries(preserved_entries, gaps_refused.entries, gaps_recorded.entries))
            for checked in (plan, gaps_refused, gaps_recorded):
                assert_artifact_target_state_plan_unchanged(project_dir, checked, expected_project_bytes=raw)
            adapter.replace_entries_atomically(restored)
            registered = {skipped_artifact_identity(key) for key in restored}
            return tuple(item for item in plan.skipped if item.identity not in registered)
    plan = plan_artifact_target_state(project_dir)
    activate_artifact_target_state(project_dir, plan=plan)
    return plan.skipped


def stage_preserved_artifact_claims(project_dir: Path, preserved: ArtifactManifestArchiveSnapshot) -> bool:
    """把归档信封里的 claim 落成暂存项目的清单，迁移链随后像原地升级一样平移它们。

    ``project.json`` 读不出时不落，返回 ``False``，由迁移链报告它。
    """

    try:
        project = json.loads((project_dir / "project.json").read_bytes().decode("utf-8"))
        if not isinstance(project, Mapping):
            return False
    except OSError, UnicodeError, ValueError:
        return False
    ProjectArtifactManifestAdapter(project_dir).replace_entries_atomically(preserved.entries)
    return True


def take_migrated_artifact_claims(
    project_dir: Path, preserved: ArtifactManifestArchiveSnapshot
) -> ArtifactManifestArchiveSnapshot:
    """读回迁移链平移后的 claim，撤下暂存清单，交给 :func:`ensure_imported_artifact_target_state`。

    内容摘要按键沿用信封。迁移给 claim 换键并搬图（如链首规整把重名资产的衍生迁到保留名下）时依据摘要
    不变、图的字节不变：新键的图若与某条依据相同、已消失的旧 claim 的内容摘要一致，就沿用这个摘要。
    迁移撤掉的 claim 一并丢弃；迁移补录的条目对不上旧 claim，不在其列，由导入激活按缺口规则重新补录。
    """

    adapter = ProjectArtifactManifestAdapter(project_dir)
    entries = adapter.snapshot_entries()
    departed: dict[str, set[str]] = {}
    for key, entry in preserved.entries.items():
        if key not in entries and key in preserved.content_digests:
            departed.setdefault(entry.basis_digest, set()).add(preserved.content_digests[key])
    digests = {key: digest for key, digest in preserved.content_digests.items() if key in entries}
    for key, entry in entries.items():
        candidates = departed.get(entry.basis_digest) if key not in preserved.entries else None
        if candidates:
            digest = read_artifact_content_digest(adapter, entry.artifact_path)
            if digest in candidates:
                digests[key] = digest
    (project_dir / MANIFEST_FILENAME).unlink(missing_ok=True)  # hard-delete: temp -- 归档导入暂存目录里给迁移链用的清单
    return ArtifactManifestArchiveSnapshot(
        entries={key: entry for key, entry in entries.items() if key in digests},
        content_digests=digests,
    )


ArchiveClaimOutcome = Literal[
    "carried_as_stale",
    "left_out_missing",
    "left_out_presentation",
    "left_out_old_version",
    "left_out_unreadable",
    "left_out_unverifiable",
    "kept_stale_inputs_changed",
]
"""导出时一条登记没能原样随包的去向。

- ``carried_as_stale``：视频或音频的正式文件在，但证明不了它就是选中版本；登记不带内容事实随包，导入后判 stale。
- ``left_out_missing``：正式文件已不在；登记不随包，导入后与源项目一样读作 missing。
- ``left_out_presentation``：字幕或呈现对不上它依据的媒体版本；登记不随包。
- ``left_out_old_version``：字幕或呈现依据的是旧媒体版本，仅当前版本的包不带那个版本；登记不随包。
- ``left_out_unreadable``：源项目里正式文件是符号链接或读不出（判 blocked），包里没有它；登记不随包，导入后读作
  missing。规划器只看得见导出副本，这一种由调用方对照源项目从 ``left_out_missing`` 改判。
- ``left_out_unverifiable``：其他证明不了的登记；不随包，文件照常在包里，导入时按文件重新判定。
- ``kept_stale_inputs_changed``：导出副本清掉悬空引用之前不是 current、清掉之后依据对上了（``source_stale_keys``）；
  按 :data:`UNPROVEN_MEDIA_BASIS_DIGEST` 随包，导入后仍判 stale，不经导出变成最新。
"""

_MEDIA_KINDS = frozenset({ArtifactKind.EPISODE_VIDEO, ArtifactKind.EPISODE_AUDIO})

UNPROVEN_MEDIA_BASIS_DIGEST = ArtifactBasis.build("archive/unproven-media", kind_version=1, inputs={}).digest
"""以 stale 随包的登记的依据摘要：不等于任何能投影出的依据，导入后不论包里的文件能否自证都判 stale。

主要用于证明不了是所选版本的视频与音频；源项目判 stale、却因导出副本的修复依据又对上的其他产物同样用它。

证明不了是所选版本的媒体随包时既不带内容事实、也不带原来的依据：否则导入端若能用包里的快照与版本记录重新证明，
这条登记就会被洗成最新（例如改写过版本记录指纹的包），再导出一次也一样。用户重新生成或切换版本时按真实依据重新登记
（ADR 0134）。
"""
_PRESENTATION_KINDS = frozenset({ArtifactKind.EPISODE_SUBTITLE, ArtifactKind.EPISODE_PRESENTATION})


@dataclass(frozen=True, slots=True)
class ArchiveClaimNotice:
    """一条没能原样随包的登记：导出不因它失败，但要让用户知道导入后它是什么状态。"""

    key: ArtifactKey
    artifact_path: str
    outcome: ArchiveClaimOutcome


@dataclass(frozen=True, slots=True)
class ArtifactManifestArchiveExport:
    """导出信封里的清单快照，连同没能原样随包的登记。"""

    snapshot: ArtifactManifestArchiveSnapshot
    notices: tuple[ArchiveClaimNotice, ...]


def snapshot_preserved_artifact_manifest(
    project_dir: Path,
    preserved_entries: Mapping[ArtifactKey, ArtifactManifestEntry],
    *,
    ships_unselected_versions: bool,
    source_stale_keys: frozenset[ArtifactKey] = frozenset(),
) -> ArtifactManifestArchiveExport:
    """Rebase preserved claims and bind them to one stable formal-byte snapshot.

    导出只管导出（ADR 0134）：证明不了的登记不让导出失败。视频与音频的正式文件在场时登记照常随包、不带内容
    事实；正式文件已不在、字幕与呈现对不上依据，或依据的旧版本快照不在包里（``ships_unselected_versions``
    为假）的登记不随包。每一条都记进 ``notices``，由调用方告诉用户。
    """

    with project_metadata_lock(project_dir):
        plan = _plan_preserved_artifact_target_state(
            project_dir,
            # 源清单里视频与音频登记的内容事实；没有事实的（导入时就判了 stale）照样列上，规划器不替它重新证明。
            preserved_content_facts={
                key: entry.content for key, entry in preserved_entries.items() if key.kind in _MEDIA_KINDS
            },
        )
        adapter = ProjectArtifactManifestAdapter(project_dir)
        rebased: dict[ArtifactKey, ArtifactManifestEntry] = {}
        notices: list[ArchiveClaimNotice] = []
        for key, archived in sorted(preserved_entries.items(), key=lambda item: item[0].encode()):
            current = plan.entries.get(key)
            artifact_path = current.artifact_path if current is not None else plan.formal_paths.get(key)
            if artifact_path is None and key in plan.unselected_media_formal_paths:
                if not ships_unselected_versions:
                    notices.append(ArchiveClaimNotice(key, archived.artifact_path, "left_out_old_version"))
                    continue
                artifact_path = plan.unselected_media_formal_paths[key]
            if artifact_path is None:
                notices.append(
                    ArchiveClaimNotice(key, archived.artifact_path, _left_out_outcome(adapter, key, archived))
                )
                continue
            already_unproven = archived.basis_digest == UNPROVEN_MEDIA_BASIS_DIGEST
            carried_as_stale = key.kind in _MEDIA_KINDS and (current is None or already_unproven)
            # 导出副本清掉了它的某个生成输入的引用才显得对上了依据（``source_stale_keys``）：不是它变新了。
            kept_stale = not carried_as_stale and (already_unproven or key in source_stale_keys)
            rebased[key] = ArtifactManifestEntry(
                artifact_path=artifact_path,
                basis_digest=UNPROVEN_MEDIA_BASIS_DIGEST if carried_as_stale or kept_stale else archived.basis_digest,
            )
            if carried_as_stale:
                notices.append(ArchiveClaimNotice(key, artifact_path, "carried_as_stale"))
            elif kept_stale:
                notices.append(ArchiveClaimNotice(key, artifact_path, "kept_stale_inputs_changed"))
        assert_artifact_target_state_plan_unchanged(project_dir, plan)
        content_digests = {
            key: read_artifact_content_digest(adapter, entry.artifact_path) for key, entry in rebased.items()
        }
        assert_artifact_target_state_plan_unchanged(project_dir, plan)
    return ArtifactManifestArchiveExport(
        snapshot=ArtifactManifestArchiveSnapshot(entries=rebased, content_digests=content_digests),
        notices=tuple(notices),
    )


def snapshot_self_proved_artifact_manifest(
    project_dir: Path,
    *,
    ships_unselected_versions: bool,
) -> ArtifactManifestArchiveExport:
    """源项目的清单读不出时，按导出规划器自己的证明组一份清单快照（ADR 0134）。

    视频与音频、依据旧媒体版本的字幕与呈现按各自记录的生成依据登记，导入后照生成时的依据判时效：已过期的仍是
    stale，不会变成 missing 或最新。视频与音频的正式文件在、证明不成立（含没有版本记录）时以
    :data:`UNPROVEN_MEDIA_BASIS_DIGEST` 随包，导入后判 stale。其余产物没有别处记着生成依据，按当前内容投影登记，
    导入后判 current。
    """

    with project_metadata_lock(project_dir):
        plan = _plan_preserved_artifact_target_state(project_dir)
        adapter = ProjectArtifactManifestAdapter(project_dir)
        entries: dict[ArtifactKey, ArtifactManifestEntry] = {}
        notices: list[ArchiveClaimNotice] = []
        for key, planned in plan.entries.items():
            recorded = plan.recorded_basis_digests.get(key) if key.kind in _MEDIA_KINDS else None
            entries[key] = ArtifactManifestEntry(
                artifact_path=planned.artifact_path, basis_digest=recorded or planned.basis_digest
            )
        unproven = {key: path for key, path in plan.formal_paths.items() if key not in entries}
        if ships_unselected_versions:
            unproven.update(plan.unselected_media_formal_paths)
        for key, artifact_path in sorted(unproven.items(), key=lambda item: item[0].encode()):
            if key.kind in _MEDIA_KINDS:
                # 正式文件在、证明不了是所选版本的视频与音频（含没有版本记录、记不出依据的）：以 stale 随包。
                entries[key] = ArtifactManifestEntry(
                    artifact_path=artifact_path, basis_digest=UNPROVEN_MEDIA_BASIS_DIGEST
                )
                notices.append(ArchiveClaimNotice(key, artifact_path, "carried_as_stale"))
                continue
            recorded = plan.recorded_basis_digests.get(key)
            if recorded is None:
                notices.append(ArchiveClaimNotice(key, artifact_path, "left_out_unverifiable"))
                continue
            entries[key] = ArtifactManifestEntry(artifact_path=artifact_path, basis_digest=recorded)
        assert_artifact_target_state_plan_unchanged(project_dir, plan)
        content_digests = {
            key: read_artifact_content_digest(adapter, entry.artifact_path) for key, entry in entries.items()
        }
        assert_artifact_target_state_plan_unchanged(project_dir, plan)
    return ArtifactManifestArchiveExport(
        snapshot=ArtifactManifestArchiveSnapshot(entries=entries, content_digests=content_digests),
        notices=tuple(notices),
    )


def _left_out_outcome(
    adapter: ProjectArtifactManifestAdapter, key: ArtifactKey, archived: ArtifactManifestEntry
) -> ArchiveClaimOutcome:
    observation = adapter.inspect_artifact(archived.artifact_path)
    if observation.blocker is None and not observation.present:
        return "left_out_missing"
    if key.kind in _PRESENTATION_KINDS:
        return "left_out_presentation"
    return "left_out_unverifiable"


def _archived_content_evidence(
    adapter: ProjectArtifactManifestAdapter,
    artifact_path: str,
    archived_digest: str,
) -> Literal["exact", "text_mode", "mismatch"]:
    """Classify whether the archived content digest binds a claim to the imported bytes.

    Archives exported through a text-mode descriptor hashed CRLF folded to LF and stopped at
    the first ``0x1A``.  Both translations drop bytes, so such a digest cannot prove the whole
    artifact; it only shows the bytes came through that export path.  Both digests come from
    one streamed read so large formal media is never buffered.
    """

    text_mode = TextModeDigest()
    if read_artifact_content_digest(adapter, artifact_path, chunk_observer=text_mode.update) == archived_digest:
        return "exact"
    return "text_mode" if text_mode.hexdigest() == archived_digest else "mismatch"


def _plan_preserved_artifact_target_state(
    project_dir: Path,
    *,
    preserved_content_facts: Mapping[ArtifactKey, ArtifactContentFacts | None] | None = None,
) -> ArtifactTargetStatePlan:
    """Prove canonical paths while leaving preserved generation digests immutable."""

    return TargetStatePlanner(
        project_dir, allow_stale_formal_targets=True, preserved_content_facts=preserved_content_facts
    ).plan()


def _rebase_preserved_artifact_entries(
    plan: ArtifactTargetStatePlan,
    preserved_entries: Mapping[ArtifactKey, ArtifactManifestEntry],
) -> dict[ArtifactKey, ArtifactManifestEntry]:
    """导入时把信封里的 claim 落到规划器证明的正式路径上，依据摘要不变；证明不了的 claim 一律拒绝。

    依据的视频或音频已不是选中版本、对那个版本仍自证的字幕与呈现 claim 暂不适用，照常落路径。导出不走这里：
    导出对证明不了的登记照常出包并逐条告知（:func:`snapshot_preserved_artifact_manifest`）。
    """

    rebased: dict[ArtifactKey, ArtifactManifestEntry] = {}
    invalid: list[str] = []
    for key, archived in preserved_entries.items():
        current = plan.entries.get(key)
        artifact_path = current.artifact_path if current is not None else plan.formal_paths.get(key)
        if artifact_path is None:
            artifact_path = plan.unselected_media_formal_paths.get(key)
        if artifact_path is None:
            invalid.append(key.encode())
            continue
        rebased[key] = ArtifactManifestEntry(
            artifact_path=artifact_path,
            basis_digest=archived.basis_digest,
        )
    if invalid:
        raise ValueError(f"archive Artifact Manifest contains unprovable formal claims: {sorted(invalid)}")
    return rebased


def reconcile_artifact_target_claims(
    project_dir: Path,
    keys: Sequence[ArtifactKey],
    *,
    adapter: ArtifactManifestAdapter | None = None,
) -> bool:
    """Forget claims whose canonical target disappeared or moved.

    Metadata edits may remove a formal target without touching its artifact
    bytes.  Resolve the selected claims against one frozen project snapshot,
    verify every dependency remains unchanged, then remove the invalid claims
    in one Manifest compare-and-swap.  Claims whose path is still canonical are
    deliberately retained: changed inputs make them stale, not unowned.
    """

    requested = tuple(dict.fromkeys(keys))
    if not requested:
        return False

    storage = adapter or ProjectArtifactManifestAdapter(project_dir)
    manifest_snapshot = storage.snapshot_entries()
    claimed = {key: manifest_snapshot[key] for key in requested if key in manifest_snapshot}
    if not claimed:
        return False

    replacements, plan = _plan_artifact_claim_reconciliation(project_dir, claimed)
    if not replacements:
        return False
    assert_artifact_target_state_plan_unchanged(project_dir, plan)
    return register_artifact_entries_atomically(
        project_dir,
        replacements,
        expected_entries={key: claimed[key] for key in replacements},
        adapter=storage,
    )


def _plan_artifact_claim_reconciliation(
    project_dir: Path,
    claimed: Mapping[ArtifactKey, ArtifactManifestEntry],
) -> tuple[dict[ArtifactKey, None], ArtifactTargetStatePlan]:
    """Resolve claimed paths through one canonical dependency snapshot."""

    shared_versions = SharedVersionMetadata()
    root_planner = TargetStatePlanner(project_dir, shared_versions=shared_versions)
    planners: dict[int | None, TargetStatePlanner] = {None: root_planner}
    dependency_bytes: dict[Path, bytes] = {}
    dependency_digests: dict[Path, str] = {}
    replacements: dict[ArtifactKey, None] = {}

    def _merge_dependency_snapshot[T](destination: dict[Path, T], source: Mapping[Path, T]) -> None:
        for path, value in source.items():
            previous = destination.setdefault(path, value)
            if previous != value:
                raise ArtifactTargetStateChangedError(
                    f"artifact target dependency changed during reconciliation: {path}"
                )

    for key, frozen_entry in claimed.items():
        scope = episode_scope_for_key(key)
        planner = planners.get(scope)
        if planner is None:
            planner = TargetStatePlanner(
                project_dir,
                episode_scope=scope,
                project_bytes=root_planner.project_bytes,
                shared_versions=shared_versions,
            )
            planners[scope] = planner
        target = planner.resolve_key(key)
        if target is None or target.artifact_path != frozen_entry.artifact_path:
            replacements[key] = None

    for planner in planners.values():
        _merge_dependency_snapshot(dependency_bytes, planner.dependencies)
        _merge_dependency_snapshot(dependency_digests, planner.dependency_digests)
    return (
        replacements,
        ArtifactTargetStatePlan(
            entries={},
            formal_paths={},
            project=root_planner.project,
            project_bytes=root_planner.project_bytes,
            dependency_bytes=dependency_bytes,
            dependency_digests=dependency_digests,
            script_paths=(),
        ),
    )


def prepare_episode_script_manifest_commit(
    project_dir: Path,
    *,
    episode: int,
    artifact_path: str,
    resource_ids: Sequence[str],
    removed_resource_ids: Sequence[str] = (),
    basis: ArtifactBasis | ArtifactBasisDescriptor | None = None,
    adapter: ArtifactManifestAdapter | None = None,
) -> Callable[[], None] | None:
    """Preflight one script replacement and return its atomic claim commit.

    The script claim and every claim orphaned by removal share one Manifest
    compare-and-swap. Callers invoke the returned closure
    inside the same formal-write transaction that selects the script bytes.
    """

    if type(episode) is not int or episode < 1:
        raise ValueError("episode must be a positive integer")
    remaining_ids = frozenset(resource_ids)
    removed_ids = frozenset(removed_resource_ids)
    if any(not resource_id for resource_id in (*remaining_ids, *removed_ids)):
        raise ValueError("script resource identities must be non-empty strings")

    storage = adapter or ProjectArtifactManifestAdapter(project_dir)
    snapshot = storage.snapshot_entries()
    observation = storage.inspect_artifact(artifact_path)
    if observation.blocker is not None:
        raise ArtifactManifestError(observation.blocker.detail)
    script_key = ArtifactKey.episode_script(episode)
    orphaned_keys = [
        key
        for key in snapshot
        if key.episode_number == episode
        and key.kind in _EPISODE_RESOURCE_KINDS
        and cast(str, key.components[1]) not in remaining_ids
    ]
    orphaned_keys.extend(
        key
        for resource_id in sorted(removed_ids - remaining_ids)
        for key in ArtifactKey.episode_resource_artifacts(episode, resource_id)
    )
    orphaned_keys = list(dict.fromkeys(orphaned_keys))
    grid_claims = {
        key: entry
        for key, entry in snapshot.items()
        if key.kind is ArtifactKind.EPISODE_GRID and key.episode_number == episode
    }
    expected = {key: snapshot.get(key) for key in (script_key, *orphaned_keys)}
    expected.update(grid_claims)
    frozen_entry: ArtifactManifestEntry | None = None
    if basis is not None:
        descriptor = basis if isinstance(basis, ArtifactBasisDescriptor) else ArtifactBasisDescriptor.from_basis(basis)
        frozen_entry = ArtifactManifestEntry(artifact_path=artifact_path, basis_digest=descriptor.digest)

    def commit() -> None:
        replacements: dict[ArtifactKey, ArtifactManifestEntry | None] = dict.fromkeys(orphaned_keys)
        if grid_claims:
            grid_replacements, grid_plan = _plan_artifact_claim_reconciliation(project_dir, grid_claims)
            assert_artifact_target_state_plan_unchanged(project_dir, grid_plan)
            replacements.update(grid_replacements)
        replacements[script_key] = frozen_entry or resolve_current_artifact_target(project_dir, script_key)
        register_artifact_entries_atomically(
            project_dir,
            replacements,
            expected_entries=expected,
            adapter=storage,
        )

    return commit


def assert_artifact_target_state_plan_unchanged(
    project_dir: Path,
    plan: ArtifactTargetStatePlan,
    *,
    expected_project_bytes: bytes | None = None,
) -> None:
    """Reject a target-state plan when any project input has drifted since planning."""
    _assert_project_unchanged(
        project_dir,
        plan.project_bytes if expected_project_bytes is None else expected_project_bytes,
    )
    for path, expected in plan.dependency_bytes.items():
        try:
            current = path.read_bytes()
        except OSError as exc:
            raise ArtifactTargetStateChangedError(
                f"artifact activation dependency changed after preflight: {path}"
            ) from exc
        if current != expected:
            raise ArtifactTargetStateChangedError(f"artifact activation dependency changed after preflight: {path}")
    for path, expected in plan.dependency_digests.items():
        try:
            current = visual_file_digest(path)
        except OSError as exc:
            raise ArtifactTargetStateChangedError(
                f"artifact activation dependency changed after preflight: {path}"
            ) from exc
        if current != expected:
            raise ArtifactTargetStateChangedError(f"artifact activation dependency changed after preflight: {path}")


def _assert_project_unchanged(project_dir: Path, expected: bytes) -> None:
    try:
        current = (project_dir / "project.json").read_bytes()
    except OSError as exc:
        raise ArtifactTargetStateChangedError("project.json changed after artifact activation preflight") from exc
    if current != expected:
        raise ArtifactTargetStateChangedError("project.json changed after artifact activation preflight")


__all__ = [
    "UNPROVEN_MEDIA_BASIS_DIGEST",
    "ArchiveClaimNotice",
    "ArchiveClaimOutcome",
    "ArtifactComparer",
    "ArtifactCurrencyResolver",
    "ArtifactInputClaim",
    "ArtifactManifestArchiveExport",
    "ArtifactTargetStateChangedError",
    "ArtifactTargetStatePlan",
    "EpisodeScriptInput",
    "RegisteredArtifactResolver",
    "activate_artifact_target_state",
    "active_artifact_currency_resolver",
    "artifact_input_is_usable",
    "artifact_is_usable",
    "artifact_key_for_resource",
    "assert_artifact_input_claims_usable",
    "assert_artifact_target_state_plan_unchanged",
    "assert_current_artifact_input_claims_usable",
    "bind_artifact_input_claims_to_content_digests",
    "bind_artifact_input_claims_to_frozen_visuals",
    "ensure_imported_artifact_target_state",
    "forget_current_resource_artifact",
    "forget_unbound_grid_artifacts",
    "forget_unbound_storyboard_artifacts",
    "plan_artifact_target_state",
    "prepare_episode_script_manifest_commit",
    "reconcile_artifact_target_claims",
    "register_artifact_entries_atomically",
    "register_current_artifact",
    "register_current_artifact_if_provable",
    "register_current_resource_artifact",
    "register_task_current_resource_artifact",
    "resolve_artifact_episode",
    "resolve_current_artifact_basis",
    "resolve_current_artifact_target",
    "resolve_current_resource_artifact_basis",
    "resolve_usable_artifact_input_claim",
    "resolve_usable_episode_script_input",
    "resolve_usable_storyboard_video_inputs",
    "snapshot_preserved_artifact_manifest",
    "snapshot_self_proved_artifact_manifest",
    "snapshot_usable_artifact_input_claim",
    "stage_preserved_artifact_claims",
    "take_migrated_artifact_claims",
]
