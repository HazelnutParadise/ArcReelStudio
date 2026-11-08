"""Agent 用哪个引擎跑新会话：Claude（Claude Agent SDK）、Codex（ChatGPT 订阅 / OpenAI API Key）或 Grok（Grok 订阅 /
xAI API Key），以及 Codex、Grok 各用哪条连线与哪个模型。整个工作区共用，只有管理员能改；已经存在的会话照它当初的引擎恢复
（docs/adr/0124、0125）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lib.config.repository import SystemSettingRepository
from lib.db import get_async_session
from lib.db.repositories.credential_repository import CredentialRepository
from server.agent_runtime.codex_engine import (
    AGENT_ENGINE_SETTING_KEY,
    CODEX_CREDENTIAL_SETTING_KEY,
    CODEX_MODEL_SETTING_KEY,
    CODEX_PROVIDERS,
    DEFAULT_CODEX_MODEL,
    AgentEngine,
    codex_connection,
    parse_agent_engine,
)
from server.agent_runtime.grok_engine import (
    DEFAULT_GROK_MODEL,
    GROK_CREDENTIAL_SETTING_KEY,
    GROK_MODEL_SETTING_KEY,
    GROK_MODELS,
    GROK_PROVIDERS,
    grok_connection,
)
from server.auth import AdminUser
from server.i18n import Translator

router = APIRouter(prefix="/agent/engine", tags=["Agent 配置"])

#: Codex 引擎可选的模型（与 ChatGPT 订阅文字生成清单一致）
CODEX_MODELS: tuple[str, ...] = ("gpt-5.5", "gpt-6-sol", "gpt-6-luna")


class EngineStatus(BaseModel):
    engine: AgentEngine
    #: 设定里指定的 Codex 连线；``None`` 表示用预设（ChatGPT 订阅优先，再来 OpenAI）
    codex_credential_id: int | None
    #: 新的 Codex 会话实际会用的连线；没有可用连线时为 ``None``
    codex_effective_credential_id: int | None
    codex_model: str
    codex_models: list[str]
    grok_credential_id: int | None
    grok_effective_credential_id: int | None
    grok_model: str
    grok_models: list[str]


class EngineRequest(BaseModel):
    engine: AgentEngine
    codex_credential_id: int | None = None
    codex_model: str = Field(default=DEFAULT_CODEX_MODEL, min_length=1, max_length=64)
    grok_credential_id: int | None = None
    grok_model: str = Field(default=DEFAULT_GROK_MODEL, min_length=1, max_length=64)


async def _status(session: AsyncSession) -> EngineStatus:
    settings = await SystemSettingRepository(session).get_all()
    raw = (settings.get(CODEX_CREDENTIAL_SETTING_KEY) or "").strip()
    effective = await codex_connection(session, settings)
    grok_raw = (settings.get(GROK_CREDENTIAL_SETTING_KEY) or "").strip()
    grok_effective = await grok_connection(session, settings)
    return EngineStatus(
        engine=parse_agent_engine(settings.get(AGENT_ENGINE_SETTING_KEY)),
        codex_credential_id=int(raw) if raw.isdigit() else None,
        codex_effective_credential_id=effective.id if effective is not None else None,
        codex_model=(settings.get(CODEX_MODEL_SETTING_KEY) or "").strip() or DEFAULT_CODEX_MODEL,
        codex_models=list(CODEX_MODELS),
        grok_credential_id=int(grok_raw) if grok_raw.isdigit() else None,
        grok_effective_credential_id=grok_effective.id if grok_effective is not None else None,
        grok_model=(settings.get(GROK_MODEL_SETTING_KEY) or "").strip() or DEFAULT_GROK_MODEL,
        grok_models=list(GROK_MODELS),
    )


@router.get("", response_model=EngineStatus)
async def get_engine(session: AsyncSession = Depends(get_async_session)) -> EngineStatus:
    return await _status(session)


@router.put("", response_model=EngineStatus)
async def set_engine(
    body: EngineRequest,
    _admin: AdminUser,
    _t: Translator,
    session: AsyncSession = Depends(get_async_session),
) -> EngineStatus:
    repo = SystemSettingRepository(session)
    if body.codex_model not in CODEX_MODELS:
        raise HTTPException(status_code=422, detail=_t("codex_model_not_supported", model=body.codex_model))
    if body.grok_model not in GROK_MODELS:
        raise HTTPException(status_code=422, detail=_t("grok_model_not_supported", model=body.grok_model))
    if body.grok_credential_id is not None:
        chosen_grok = await CredentialRepository(session).get_by_id(body.grok_credential_id)
        if chosen_grok is None or chosen_grok.provider not in GROK_PROVIDERS:
            raise HTTPException(status_code=422, detail=_t("grok_credential_not_found"))
    if body.codex_credential_id is not None:
        chosen = await CredentialRepository(session).get_by_id(body.codex_credential_id)
        if chosen is None or chosen.provider not in CODEX_PROVIDERS:
            raise HTTPException(status_code=422, detail=_t("codex_credential_not_found"))
    if body.engine == "codex":
        settings = await repo.get_all()
        settings[CODEX_CREDENTIAL_SETTING_KEY] = str(body.codex_credential_id or "")
        if await codex_connection(session, settings) is None:
            raise HTTPException(status_code=422, detail=_t("codex_connection_required"))
    if body.engine == "grok":
        settings = await repo.get_all()
        settings[GROK_CREDENTIAL_SETTING_KEY] = str(body.grok_credential_id or "")
        if await grok_connection(session, settings) is None:
            raise HTTPException(status_code=422, detail=_t("grok_connection_required"))
    await repo.set(AGENT_ENGINE_SETTING_KEY, body.engine)
    await repo.set(CODEX_CREDENTIAL_SETTING_KEY, str(body.codex_credential_id or ""))
    await repo.set(CODEX_MODEL_SETTING_KEY, body.codex_model)
    await repo.set(GROK_CREDENTIAL_SETTING_KEY, str(body.grok_credential_id or ""))
    await repo.set(GROK_MODEL_SETTING_KEY, body.grok_model)
    await session.commit()
    return await _status(session)
