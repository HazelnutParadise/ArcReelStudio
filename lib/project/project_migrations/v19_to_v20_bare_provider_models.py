"""v19→v20 迁移：项目模型字段里只写了内置供应商、没写模型的旧值，改写为 ``provider/推荐模型``。

升级前的运行时把这类裸供应商（含 ``"openai/"`` 这样缺模型的脏值）按模型目录里该供应商的默认模型补全，目录一改，
生成用的模型就跟着变。现在目录里的默认模型只作推荐，运行时不再补全（docs/adr/0130），本步按迁移这一刻目录的推荐
写下模型，之后不再随目录变化。启动时目录的三层数据先于项目迁移装入（``server.app``）。

- 只改写文本、图片、视频与配音字段（含任务类型桶与文本档位）；``music_backend`` 与 ``sfx_backend`` 的裸值原样
  保留，音乐与音效没有推荐。配音字段只用有文本转语音能力的推荐，推荐是音乐模型时原样保留。
- 没有推荐的、自定义供应商的裸 id、不认识的供应商、完整的 ``provider/model`` 与非字符串值原样保留，运行时报
  「没有选定模型」，由用户重新选择。连线旁键（``<字段>_credential_id``）不动：字段只补模型，供应商不变。
- 归档导入另外跳过用户停用的推荐（``excluded``，由导入入口查库后传入），其余入口直接用目录的推荐。

只改 ``project.json``，备份由 runner 负责；``metadata.updated_at`` 原样保留。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lib.artifacts.formal_write import project_metadata_lock
from lib.catalog import query as catalog
from lib.config.model_setting_keys import (
    MODEL_SETTING_CAPABILITIES,
    MODEL_SETTING_MEDIA_TYPES,
    PROJECT_MODEL_SETTING_KEYS,
)
from lib.config.registry import PROVIDER_REGISTRY
from lib.infra.json_io import atomic_write_json
from lib.project.project_schema import parse_project_schema_version

TARGET_SCHEMA_VERSION = 20

#: 供应商 id → 不能写进项目的推荐模型键（归档导入时是用户停用的模型）。
ExcludedRecommendations = Mapping[str, frozenset[str]]

#: 改写的字段：音乐与音效没有推荐，不在其中。
_REWRITTEN_KEYS: tuple[str, ...] = tuple(
    key for key in PROJECT_MODEL_SETTING_KEYS if key not in {"music_backend", "sfx_backend"}
)


def _bare_builtin_provider(value: object) -> str | None:
    """裸内置供应商（``"ark"``、``"ark/"``、两端带空白）→ 供应商 id；完整的 ``provider/model`` 与其他值为 None。"""
    if not isinstance(value, str):
        return None
    provider, sep, model = value.partition("/")
    if sep and provider.strip() and model.strip():
        return None
    provider = provider.strip()
    return provider if provider in PROVIDER_REGISTRY else None


def _recommendation(provider_id: str, key: str, excluded: ExcludedRecommendations) -> str | None:
    """供应商给这个字段的推荐模型：目录此刻的默认模型，具备字段要求的能力（配音须能文本转语音），且不在排除之列。"""
    model_id = catalog.default_model(provider_id, MODEL_SETTING_MEDIA_TYPES[key])
    if model_id is None or model_id in excluded.get(provider_id, frozenset()):
        return None
    required = MODEL_SETTING_CAPABILITIES.get(key)
    if required is not None:
        model_info = catalog.get_model(provider_id, model_id)
        if model_info is None or required not in model_info.capabilities:
            return None
    return model_id


def migrate_project_dict(project: Mapping[str, Any], excluded: ExcludedRecommendations | None = None) -> dict[str, Any]:
    """纯函数：把裸内置供应商的模型字段改写为 ``provider/推荐模型``。幂等。

    ``excluded`` 里的推荐不用，字段原样保留。不改 schema_version（由文件级 migrate 提交时写入）。
    """
    excluded = excluded or {}
    migrated = dict(project)
    for key in _REWRITTEN_KEYS:
        provider = _bare_builtin_provider(migrated.get(key))
        if provider is None:
            continue
        model = _recommendation(provider, key, excluded)
        if model is not None:
            migrated[key] = f"{provider}/{model}"
    return migrated


def migrate_v19_to_v20(project_dir: Path, *, excluded: ExcludedRecommendations | None = None) -> None:
    """v19→v20 文件级迁移。单次原子写，崩溃可重试（要么旧值要么新值，无半态）。"""

    project_file = Path(project_dir) / "project.json"
    if not project_file.is_file():
        return
    with project_metadata_lock(project_dir):
        project = json.loads(project_file.read_bytes())
        if not isinstance(project, dict):
            raise ValueError("project.json 必须是对象")
        if parse_project_schema_version(project) >= TARGET_SCHEMA_VERSION:
            return
        atomic_write_json(
            project_file, {**migrate_project_dict(project, excluded), "schema_version": TARGET_SCHEMA_VERSION}
        )


__all__ = ["TARGET_SCHEMA_VERSION", "ExcludedRecommendations", "migrate_project_dict", "migrate_v19_to_v20"]
