from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from arcreel_market_core.video_backend_contract import DEFAULT_VIDEO_POLL_TIMEOUT_SECONDS
from lib.agent.agent_auth import (
    AUTH_MODE_SETTING_KEY,
    AuthSource,
    auth_availability,
    choose_auth_source,
    fallback_source,
    parse_auth_mode,
)
from lib.agent.credential_tiers import TIERS, AgentPricing, Tier, agent_pricing, tier_models
from lib.catalog import query as catalog
from lib.catalog.builtin_models import disabled_builtin_models
from lib.config.env_keys import ANTHROPIC_ENV_KEYS
from lib.config.registry import PROVIDER_REGISTRY
from lib.config.repository import ProviderConfigRepository, SystemSettingRepository
from lib.db.models.credential import ProviderCredential
from lib.db.repositories.credential_repository import CredentialRepository
from lib.infra.schema_guards import is_int

# 旁白默认音色（DashScope 预设）；全局 setting 未配置时的兜底。全局音色与语速只作为新建 TTS 项目
# 的预填值，项目创建后以 project.json 顶层的快照为准（docs/adr/0089）。
_DEFAULT_NARRATION_VOICE = "Cherry"
MIN_VIDEO_POLL_TIMEOUT_SECONDS = 60

# 参考上传副本的保守通用请求体上限（ArcReel 侧安全策略常量，非任一供应商的真实字节限；
# 被动 413 兜底负责自我纠正）。可经 per-provider 配置 key 覆盖。
# 与 lib/references/reference_compression.DEFAULT_* 数值一致（单测断言对齐）。
DEFAULT_REFERENCE_TOTAL_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_REFERENCE_SINGLE_MAX_BYTES = 4 * 1024 * 1024

# 写入层校验为正整数的容量键（与 CapacityTable 的三条 lane 一一对应）。
# 其余 number 字段（image_rpm / video_rpm / request_gap）语义不同（允许小数），不在此列。
_MAX_WORKERS_KEYS = frozenset({"image_max_workers", "video_max_workers", "audio_max_workers"})
_MAX_WORKERS_CODE = "max_workers_must_be_positive_integer"


class ProviderConfigValueError(ValueError):
    """provider 配置值校验失败。

    携带 i18n message code + 渲染参数（key 而非译文），router 层 ``_t(exc.code, **exc.params)``
    泛化翻译为 user-facing 文案，无需感知具体校验规则。
    """

    def __init__(self, provider: str, key: str, value: str, *, code: str) -> None:
        super().__init__(f"invalid value for {provider}.{key}: {value!r} ({code})")
        self.provider = provider
        self.key = key
        self.value = value
        self.code = code
        self.params: dict[str, str] = {"field": key, "value": value}


# 档位 → 环境变量名。
_TIER_ENV_KEYS: dict[Tier, str] = {
    "model": "ANTHROPIC_MODEL",
    "haiku": "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "sonnet": "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "opus": "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "subagent": "CLAUDE_CODE_SUBAGENT_MODEL",
}


#: Claude 订阅登录换来的长效令牌经这个环境变量交给 CLI
OAUTH_TOKEN_ENV_KEY = "CLAUDE_CODE_OAUTH_TOKEN"


@dataclass(frozen=True)
class AnthropicEnv:
    """注入 Agent 会话的认证环境变量，以及计价依据（没有生效凭证时为默认值）与这次用的认证来源。"""

    env: dict[str, str]
    pricing: AgentPricing
    source: AuthSource = "api_key"


#: Agent 用哪一条 Claude 订阅连线（``provider_credential`` id）；没设或那条连线已不在时用 Claude 订阅的默认连线
AGENT_SUBSCRIPTION_CREDENTIAL_KEY = "agent_subscription_credential_id"
CLAUDE_SUBSCRIPTION_PROVIDER = "claude-subscription"


async def agent_claude_subscription(
    session: AsyncSession, settings: Mapping[str, str] | None = None
) -> ProviderCredential | None:
    """Agent 会话用的 Claude 订阅连线；一条都没有时为 ``None``。"""
    if settings is None:
        settings = await SystemSettingRepository(session).get_all()
    repo = CredentialRepository(session)
    raw = (settings.get(AGENT_SUBSCRIPTION_CREDENTIAL_KEY) or "").strip()
    if raw.isdigit():
        chosen = await repo.get_by_id(int(raw))
        if chosen is not None and chosen.provider == CLAUDE_SUBSCRIPTION_PROVIDER and chosen.api_key:
            return chosen
    default = await repo.get_active(CLAUDE_SUBSCRIPTION_PROVIDER)
    return default if default is not None and default.api_key else None


async def build_anthropic_env(session: AsyncSession) -> AnthropicEnv:
    """从 DB 读 active credential，返回 {ENV_KEY: value} 与计价依据快照，**不写 os.environ**。

    返回值由 OptionsAssembler 的凭证注入（load_provider_env_overrides）注入到 ClaudeAgentOptions.env。凭证只读一次，
    环境变量与计价依据（凭证 id、倍率、档位绑定）取自同一行：会话按连接时注入的凭证计价（docs/adr/0102）。

    密钥与地址只来自生效的 Agent 供应商凭证；没有生效凭证时每个 Anthropic 环境变量都置空。档位模型名的规则见
    :func:`lib.agent.credential_tiers.tier_models`。
    """
    # 局部 import 避免循环依赖（agent_credential_repo → agent_credential model → base）
    from lib.db.repositories.agent_credential_repo import AgentCredentialRepository

    cred = await AgentCredentialRepository(session).get_active()
    settings = await SystemSettingRepository(session).get_all()
    subscription = await agent_claude_subscription(session, settings)

    has_api_key = bool(cred is not None and cred.api_key)
    source = choose_auth_source(
        parse_auth_mode(settings.get(AUTH_MODE_SETTING_KEY)),
        has_api_key=has_api_key,
        has_subscription=subscription is not None,
        availability=auth_availability,
    )

    if source == "subscription" and subscription is not None:
        # 订阅会话只带令牌：API Key 凭证的地址、密钥与档位模型都不带进来，模型由 CLI 按订阅默认值选；
        # 订阅额度不按 token 计费，倍率记 0
        env = dict.fromkeys(ANTHROPIC_ENV_KEYS, "")
        env[OAUTH_TOKEN_ENV_KEY] = subscription.api_key or ""
        return AnthropicEnv(
            env=env,
            pricing=AgentPricing(multiplier=0.0, subscription_credential_id=subscription.id),
            source="subscription",
        )

    if cred is not None:
        models = tier_models(cred, settings)
        env = {
            "ANTHROPIC_API_KEY": cred.api_key or "",
            "ANTHROPIC_BASE_URL": cred.base_url or "",
            **{_TIER_ENV_KEYS[tier]: models[tier] for tier in TIERS},
            OAUTH_TOKEN_ENV_KEY: "",
        }
        return AnthropicEnv(env=env, pricing=agent_pricing(cred, settings))

    return AnthropicEnv(env={**dict.fromkeys(ANTHROPIC_ENV_KEYS, ""), OAUTH_TOKEN_ENV_KEY: ""}, pricing=AgentPricing())


async def auth_fallback_for(session: AsyncSession, current: AuthSource) -> AuthSource | None:
    """``current`` 不能用时，按目前的认证方式与配置可以改用的另一方；不能改用时为 ``None``。"""
    from lib.db.repositories.agent_credential_repo import AgentCredentialRepository

    cred = await AgentCredentialRepository(session).get_active()
    settings = await SystemSettingRepository(session).get_all()
    subscription = await agent_claude_subscription(session, settings)
    has_api_key = bool(cred is not None and cred.api_key)
    return fallback_source(
        parse_auth_mode(settings.get(AUTH_MODE_SETTING_KEY)),
        current,
        has_api_key=has_api_key,
        has_subscription=subscription is not None,
    )


@dataclass
class ProviderStatus:
    name: str
    display_name: str
    status: Literal["ready", "unconfigured", "error"]
    media_types: list[str]
    capabilities: list[str]
    required_keys: list[str]
    # 凭证（界面称「密钥」）条数，供设置页二级栏显示「已配置 N 个密钥」。
    credential_count: int
    models: dict[str, dict] | None = None  # model_id -> CatalogModel 的 dict 形态
    # 不作候选的模型键（用户停用的，加上已下线的）：不出现在默认模型设置的候选里，也不被自动挑选（docs/adr/0099）。
    disabled_models: frozenset[str] = frozenset()


class ConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self._provider_repo = ProviderConfigRepository(session)
        self._setting_repo = SystemSettingRepository(session)

    async def get_provider_config(self, provider: str) -> dict[str, str]:
        self._validate_provider(provider)
        return await self._provider_repo.get_all(provider)

    async def set_provider_config(
        self,
        provider: str,
        key: str,
        value: str,
        *,
        flush: bool = True,
    ) -> None:
        self._validate_provider(provider)
        self._validate_value(provider, key, value)
        if key in _MAX_WORKERS_KEYS:
            # 入库统一规范化为 ASCII 数字串（int() 接受 " 5 " / "+5" / "1_0" / 全角数字等
            # 非规范形态），保证任何读取方拿到的都是可直接解析、可在 number 输入框回显的值
            value = str(int(value))
        meta = PROVIDER_REGISTRY[provider]
        is_secret = key in meta.secret_keys
        await self._provider_repo.set(provider, key, value, is_secret=is_secret, flush=flush)

    async def delete_provider_config(
        self,
        provider: str,
        key: str,
        *,
        flush: bool = True,
    ) -> None:
        self._validate_provider(provider)
        await self._provider_repo.delete(provider, key, flush=flush)

    async def get_all_providers_status(self) -> list[ProviderStatus]:
        cred_repo = CredentialRepository(self._provider_repo.session)
        active_creds = await cred_repo.get_active_credentials_bulk()
        credential_counts = await cred_repo.count_by_provider_bulk()
        disabled = await disabled_builtin_models(self._provider_repo.session)
        statuses = []
        for name, meta in PROVIDER_REGISTRY.items():
            status: Literal["ready", "unconfigured", "error"] = "ready" if name in active_creds else "unconfigured"
            # asdict 深拷贝 list/dict 字段，返回值不与模型目录共享引用，调用方改写不会波及目录。
            models_dict = {mid: asdict(mi) for mid, mi in catalog.list_models(name).items()}
            statuses.append(
                ProviderStatus(
                    name=name,
                    display_name=meta.display_name,
                    status=status,
                    media_types=catalog.provider_media_types(name),
                    capabilities=catalog.provider_capabilities(name),
                    required_keys=list(meta.required_keys),
                    credential_count=credential_counts.get(name, 0),
                    models=models_dict,
                    disabled_models=disabled.get(name, frozenset()),
                )
            )
        return statuses

    async def get_all_provider_configs(self) -> dict[str, dict[str, str]]:
        """Get raw config for ALL providers in a single query."""
        return await self._provider_repo.get_all_configs_bulk()

    async def get_provider_config_masked(self, provider: str) -> dict[str, dict]:
        self._validate_provider(provider)
        return await self._provider_repo.get_all_masked(provider)

    async def get_setting(self, key: str, default: str = "") -> str:
        return await self._setting_repo.get(key, default)

    async def get_all_settings(self) -> dict[str, str]:
        """Get all system settings in a single query."""
        return await self._setting_repo.get_all()

    async def set_setting(self, key: str, value: str) -> None:
        await self._setting_repo.set(key, value)

    async def get_video_poll_timeout_seconds(self) -> int:
        raw = await self._setting_repo.get(
            "video_poll_timeout_seconds",
            str(DEFAULT_VIDEO_POLL_TIMEOUT_SECONDS),
        )
        return self.parse_video_poll_timeout_seconds(raw)

    @staticmethod
    def parse_video_poll_timeout_seconds(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError:
            return DEFAULT_VIDEO_POLL_TIMEOUT_SECONDS
        return value if value >= MIN_VIDEO_POLL_TIMEOUT_SECONDS else DEFAULT_VIDEO_POLL_TIMEOUT_SECONDS

    async def set_video_poll_timeout_seconds(self, value: int) -> None:
        if not is_int(value, minimum=MIN_VIDEO_POLL_TIMEOUT_SECONDS):
            raise ValueError(
                f"video poll timeout must be an integer of at least {MIN_VIDEO_POLL_TIMEOUT_SECONDS} seconds"
            )
        await self._setting_repo.set("video_poll_timeout_seconds", str(value))

    async def get_narration_voice(self) -> str:
        # 空白 setting 视为未配置，与项目级覆盖的 strip 语义一致，避免空音色进 TTS 请求
        raw = await self._setting_repo.get("narration_voice", "")
        voice = raw.strip()
        return voice or _DEFAULT_NARRATION_VOICE

    async def get_narration_speed(self) -> float | None:
        """旁白语速（全局 setting）。未设置/损坏值返回 None，由各 audio backend 按自身能力处理。"""
        raw = await self._setting_repo.get("narration_speed", "")
        return self.parse_narration_speed(raw)

    @staticmethod
    def parse_narration_speed(raw: str) -> float | None:
        """把存储态语速字符串解析为有效正有限数；空白/非数值/非正/inf/nan 一律视为未设置。"""
        text = raw.strip()
        if not text:
            return None
        try:
            speed = float(text)
        except ValueError:
            return None
        if not math.isfinite(speed) or speed <= 0:
            return None
        return speed

    @staticmethod
    def _validate_provider(provider: str) -> None:
        if provider not in PROVIDER_REGISTRY:
            raise ValueError(f"Unknown provider: {provider}")

    @staticmethod
    def _validate_value(provider: str, key: str, value: str) -> None:
        """容量键写入校验：正整数（≥1）。留空即不写该 key（回退默认），不会走到这里。

        0 不是合法用户输入——它仅作 CapacityTable 内部「不支持该 lane」哨兵，由 lane 投影
        在内存里产生，绝不写回。坏值一旦入库，容量 reload 只能逐 key 回退默认值，配置变更
        静默失效，因此在写入口拦下。
        """
        if key not in _MAX_WORKERS_KEYS:
            return
        try:
            parsed = int(value)
        except ValueError:
            raise ProviderConfigValueError(provider, key, value, code=_MAX_WORKERS_CODE) from None
        if parsed < 1:
            raise ProviderConfigValueError(provider, key, value, code=_MAX_WORKERS_CODE)


async def read_video_poll_timeout_seconds() -> int:
    """自开一个 session 读一次全局视频轮询超时。

    worker 派发与端点测试连接共用这一份：两条路径都在「即将进入一次真实生成」的时点读一次，
    各自另写一遍就会在超时含义上分叉。口径是「派发时读一次」，不是每次轮询各读各的。
    """
    from lib.db import safe_session_factory

    async with safe_session_factory() as session:
        return await ConfigService(session).get_video_poll_timeout_seconds()
