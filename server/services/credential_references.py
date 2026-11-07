"""连线（内置供应商的凭证）被哪些设置指定：删除连线前提示、确认删除后改回默认连线。

全局设置与每个项目的 ``project.json`` 里，引用模型的字段旁可以有 ``<字段>_credential_id``（见
``lib.config.model_setting_keys``）。删除被指定的连线前先列出这些位置；确认后把它们清掉，回到该供应商的默认连线。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from lib.config import resolver
from lib.config.model_setting_keys import (
    GLOBAL_MODEL_SETTING_KEYS,
    PROJECT_MODEL_SETTING_KEYS,
    credential_key,
    parse_credential_id,
)
from lib.config.service import ConfigService
from lib.infra.async_thread import run_sync_transaction

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CredentialProjectReference:
    name: str
    title: str | None
    #: 指定了这个连线的模型字段
    settings: tuple[str, ...]


@dataclass(frozen=True)
class CredentialReferences:
    #: 指定了这个连线的全局模型字段
    settings: tuple[str, ...] = ()
    projects: tuple[CredentialProjectReference, ...] = field(default_factory=tuple)

    @property
    def in_use(self) -> bool:
        return bool(self.settings or self.projects)


async def find_credential_references(session: AsyncSession, credential_id: int) -> CredentialReferences:
    all_settings = await ConfigService(session).get_all_settings()
    settings = tuple(
        key
        for key in GLOBAL_MODEL_SETTING_KEYS
        if parse_credential_id(all_settings.get(credential_key(key))) == credential_id
    )
    projects = await run_sync_transaction(_project_references, credential_id)
    return CredentialReferences(settings=settings, projects=projects)


async def clear_credential_references(session: AsyncSession, credential_id: int) -> None:
    """把指定了这个连线的全局与项目字段改回默认连线；调用方负责提交数据库事务。"""
    svc = ConfigService(session)
    all_settings = await svc.get_all_settings()
    for key in GLOBAL_MODEL_SETTING_KEYS:
        if parse_credential_id(all_settings.get(credential_key(key))) == credential_id:
            await svc.set_setting(credential_key(key), "")
    await run_sync_transaction(_clear_project_references, credential_id)


def _project_references(credential_id: int) -> tuple[CredentialProjectReference, ...]:
    pm = resolver.get_project_manager()  # 经模块属性取：用例按 lib.config.resolver 替换项目管理器
    found: list[CredentialProjectReference] = []
    for name in pm.list_projects():
        try:
            project = pm.load_project(name)
        except OSError, ValueError:
            continue
        keys = tuple(
            key
            for key in PROJECT_MODEL_SETTING_KEYS
            if parse_credential_id(project.get(credential_key(key))) == credential_id
        )
        if keys:
            title = project.get("title")
            found.append(
                CredentialProjectReference(
                    name=name, title=title if isinstance(title, str) and title else None, settings=keys
                )
            )
    return tuple(found)


def _clear_project_references(credential_id: int) -> None:
    pm = resolver.get_project_manager()

    def _mutate(project: dict) -> None:
        for key in PROJECT_MODEL_SETTING_KEYS:
            if parse_credential_id(project.get(credential_key(key))) == credential_id:
                project.pop(credential_key(key), None)

    # 只改确实指定了这个连线的项目，其他项目不产生写入与变更通知
    for reference in _project_references(credential_id):
        name = reference.name
        try:
            pm.update_project(name, _mutate)
        except Exception:
            logger.warning("清理项目 %s 指定的连线失败，已跳过", name, exc_info=True)
