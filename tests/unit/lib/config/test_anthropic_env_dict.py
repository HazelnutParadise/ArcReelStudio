"""build_anthropic_env 行为测试 — 只读 DB、返回环境变量与计价依据快照、不写 environ。"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest

from lib.agent.agent_auth import AuthAvailability
from lib.agent.credential_tiers import AgentPricing
from lib.config.env_keys import ANTHROPIC_ENV_KEYS
from lib.config.service import build_anthropic_env


@pytest.fixture(autouse=True)
def no_subscription(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """默认没有 Claude 订阅连线；需要订阅的用例改它的返回值。"""
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr("lib.config.service.agent_claude_subscription", lookup)
    monkeypatch.setattr("lib.config.service.auth_availability", AuthAvailability())
    return lookup


@pytest.mark.asyncio
async def test_active_credential_returns_full_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    repo_mock = AsyncMock()
    cred = type(
        "Cred",
        (),
        {
            "id": 7,
            "preset_id": "anthropic-official",
            "api_key": "sk-test",
            "base_url": "https://api.anthropic.com",
            "model": "claude-opus-4-7",
            "haiku_model": "claude-haiku-4-5",
            "sonnet_model": "claude-sonnet-4-6",
            "opus_model": "claude-opus-4-7",
            "subagent_model": "claude-haiku-4-5",
            "multiplier": 0.8,
            "tier_bindings": None,
        },
    )()
    repo_mock.get_active = AsyncMock(return_value=cred)

    setting_repo = AsyncMock()
    setting_repo.get_all = AsyncMock(return_value={})

    monkeypatch.setattr(
        "lib.db.repositories.agent_credential_repo.AgentCredentialRepository",
        lambda _s: repo_mock,
    )
    monkeypatch.setattr("lib.config.service.SystemSettingRepository", lambda _s: setting_repo)

    built = await build_anthropic_env(session)
    result = built.env
    assert built.pricing == AgentPricing(credential_id=7, multiplier=0.8)
    assert result["ANTHROPIC_API_KEY"] == "sk-test"
    assert result["ANTHROPIC_BASE_URL"] == "https://api.anthropic.com"
    assert result["ANTHROPIC_MODEL"] == "claude-opus-4-7"


@pytest.mark.asyncio
async def test_no_active_credential_returns_empty_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    repo_mock = AsyncMock()
    repo_mock.get_active = AsyncMock(return_value=None)

    setting_repo = AsyncMock()
    setting_repo.get_all = AsyncMock(return_value={})

    monkeypatch.setattr(
        "lib.db.repositories.agent_credential_repo.AgentCredentialRepository",
        lambda _s: repo_mock,
    )
    monkeypatch.setattr("lib.config.service.SystemSettingRepository", lambda _s: setting_repo)

    built = await build_anthropic_env(session)
    assert built.pricing == AgentPricing()
    assert built.env["ANTHROPIC_API_KEY"] == ""
    assert built.env["ANTHROPIC_BASE_URL"] == ""


@pytest.mark.asyncio
async def test_no_active_credential_ignores_keys_left_in_system_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Agent 的密钥与地址只来自 Agent 供应商凭证：系统设置里残留的旧键不注入会话。"""
    session = AsyncMock()
    repo_mock = AsyncMock()
    repo_mock.get_active = AsyncMock(return_value=None)

    legacy = {
        "anthropic_api_key": "legacy-sk",
        "anthropic_base_url": "https://legacy.anthropic.com",
        "anthropic_model": "claude-legacy-model",
    }
    setting_repo = AsyncMock()
    setting_repo.get_all = AsyncMock(return_value=legacy)

    monkeypatch.setattr(
        "lib.db.repositories.agent_credential_repo.AgentCredentialRepository",
        lambda _s: repo_mock,
    )
    monkeypatch.setattr("lib.config.service.SystemSettingRepository", lambda _s: setting_repo)

    built = await build_anthropic_env(session)
    assert built.pricing == AgentPricing()
    # 每个 Anthropic 环境变量都显式置空，进程环境里的同名变量也不会漏进会话
    assert built.env == {**dict.fromkeys(ANTHROPIC_ENV_KEYS, ""), "CLAUDE_CODE_OAUTH_TOKEN": ""}


@pytest.mark.asyncio
async def test_function_does_not_touch_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    """spec §6.3 红线：build 函数不能写 os.environ。"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    baseline = dict(os.environ)

    session = AsyncMock()
    repo_mock = AsyncMock()
    cred = type(
        "Cred",
        (),
        {
            "id": 7,
            "preset_id": "__custom__",
            "api_key": "sk-test",
            "base_url": "x",
            "model": "y",
            "haiku_model": None,
            "sonnet_model": None,
            "opus_model": None,
            "subagent_model": None,
            "multiplier": 1.0,
            "tier_bindings": None,
        },
    )()
    repo_mock.get_active = AsyncMock(return_value=cred)

    setting_repo = AsyncMock()
    setting_repo.get_all = AsyncMock(return_value={})

    monkeypatch.setattr(
        "lib.db.repositories.agent_credential_repo.AgentCredentialRepository",
        lambda _s: repo_mock,
    )
    monkeypatch.setattr("lib.config.service.SystemSettingRepository", lambda _s: setting_repo)

    await build_anthropic_env(session)
    assert dict(os.environ) == baseline, "build 函数禁止改 os.environ"


def _patch_cred(monkeypatch: pytest.MonkeyPatch, **fields: object) -> None:
    base: dict[str, object] = {
        "id": 7,
        "api_key": "sk",
        "base_url": "https://gw.example.com",
        "model": "",
        "haiku_model": "",
        "sonnet_model": "",
        "opus_model": "",
        "subagent_model": "",
        "preset_id": "deepseek",
        "multiplier": 1.0,
        "tier_bindings": None,
    }
    base.update(fields)
    cred = type("Cred", (), base)()
    repo_mock = AsyncMock()
    repo_mock.get_active = AsyncMock(return_value=cred)
    setting_repo = AsyncMock()
    setting_repo.get_all = AsyncMock(return_value={})
    monkeypatch.setattr(
        "lib.db.repositories.agent_credential_repo.AgentCredentialRepository",
        lambda _s: repo_mock,
    )
    monkeypatch.setattr("lib.config.service.SystemSettingRepository", lambda _s: setting_repo)


@pytest.mark.asyncio
async def test_non_official_preset_fills_blank_tiers_with_main_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cred(monkeypatch, model="deepseek-v4", sonnet_model="deepseek-v4-pro")
    result = (await build_anthropic_env(AsyncMock())).env
    assert result["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "deepseek-v4"
    assert result["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "deepseek-v4-pro"
    assert result["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "deepseek-v4"
    assert result["CLAUDE_CODE_SUBAGENT_MODEL"] == "deepseek-v4"


@pytest.mark.asyncio
async def test_official_preset_leaves_blank_tiers_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cred(monkeypatch, preset_id="anthropic-official", model="claude-opus-4-7", sonnet_model="claude-sonnet-4-6")
    result = (await build_anthropic_env(AsyncMock())).env
    assert result["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == ""
    assert result["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "claude-sonnet-4-6"
    assert result["ANTHROPIC_DEFAULT_OPUS_MODEL"] == ""
    assert result["CLAUDE_CODE_SUBAGENT_MODEL"] == ""


@pytest.mark.asyncio
async def test_pricing_snapshot_takes_the_multiplier_and_the_bindings_of_the_tiers_from_the_same_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """计价依据与环境变量取自同一行：倍率，以及带绑定的档位实际调用的模型名（留空档位按填充后的名字）。"""
    _patch_cred(
        monkeypatch,
        model="gw-main",
        haiku_model="GW/Fast.1",
        multiplier=0.5,
        tier_bindings={"haiku": "acme/fast-1", "opus": "acme/big", "sonnet": ""},
    )
    pricing = (await build_anthropic_env(AsyncMock())).pricing

    assert pricing.credential_id == 7
    assert pricing.multiplier == 0.5
    # 模型名比较忽略大小写与命名空间；留空的 opus 档位填成主模型，主模型档位自己没有绑定时取 opus 的绑定
    assert pricing.entry_binding_for("gw/fast-1") == "acme/fast-1"
    assert pricing.entry_binding_for("gw-main") == "acme/big"
    assert pricing.entry_binding_for("other") is None


def _patch_repos(monkeypatch: pytest.MonkeyPatch, *, cred, settings: dict[str, str]) -> None:
    repo_mock = AsyncMock()
    repo_mock.get_active = AsyncMock(return_value=cred)
    setting_repo = AsyncMock()
    setting_repo.get_all = AsyncMock(return_value=settings)
    monkeypatch.setattr("lib.db.repositories.agent_credential_repo.AgentCredentialRepository", lambda _s: repo_mock)
    monkeypatch.setattr("lib.config.service.SystemSettingRepository", lambda _s: setting_repo)


def _api_cred():
    return type(
        "Cred",
        (),
        {
            "id": 3,
            "preset_id": "anthropic-official",
            "api_key": "sk-api",
            "base_url": "https://api.anthropic.com",
            "model": "claude-opus-4-7",
            "haiku_model": None,
            "sonnet_model": None,
            "opus_model": None,
            "subagent_model": None,
            "multiplier": 1.0,
            "tier_bindings": None,
        },
    )()


def _subscription(token: str = "sk-ant-oat01-abc", credential_id: int = 7):
    return type("Sub", (), {"api_key": token, "id": credential_id})()


@pytest.mark.asyncio
async def test_subscription_session_carries_only_the_oauth_token(monkeypatch, no_subscription) -> None:
    no_subscription.return_value = _subscription()
    _patch_repos(monkeypatch, cred=_api_cred(), settings={"agent_auth_mode": "subscription"})

    built = await build_anthropic_env(AsyncMock())

    assert built.source == "subscription"
    assert built.env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-abc"
    # API Key 凭证的地址、密钥与档位模型都不带进订阅会话，模型由 CLI 按订阅默认值选
    assert built.env["ANTHROPIC_API_KEY"] == ""
    assert built.env["ANTHROPIC_BASE_URL"] == ""
    assert built.env["ANTHROPIC_MODEL"] == ""
    # 订阅额度不按 token 计费，用量记在这条订阅连线名下
    assert built.pricing == AgentPricing(multiplier=0.0, subscription_credential_id=7)


@pytest.mark.asyncio
async def test_api_key_session_blanks_the_oauth_token(monkeypatch, no_subscription) -> None:
    no_subscription.return_value = _subscription()
    _patch_repos(monkeypatch, cred=_api_cred(), settings={"agent_auth_mode": "api_key"})

    built = await build_anthropic_env(AsyncMock())

    assert built.source == "api_key"
    assert built.env["ANTHROPIC_API_KEY"] == "sk-api"
    assert built.env["CLAUDE_CODE_OAUTH_TOKEN"] == ""


@pytest.mark.asyncio
async def test_default_mode_prefers_the_subscription_when_logged_in(monkeypatch, no_subscription) -> None:
    no_subscription.return_value = _subscription()
    _patch_repos(monkeypatch, cred=_api_cred(), settings={})

    assert (await build_anthropic_env(AsyncMock())).source == "subscription"


@pytest.mark.asyncio
async def test_an_exhausted_subscription_switches_to_the_api_key(monkeypatch, no_subscription) -> None:
    availability = AuthAvailability()
    availability.mark_unavailable("subscription", until=None)
    monkeypatch.setattr("lib.config.service.auth_availability", availability)
    no_subscription.return_value = _subscription()
    _patch_repos(monkeypatch, cred=_api_cred(), settings={"agent_auth_mode": "prefer_subscription"})

    built = await build_anthropic_env(AsyncMock())

    assert built.source == "api_key"
    assert built.env["ANTHROPIC_API_KEY"] == "sk-api"


@pytest.mark.asyncio
async def test_without_a_subscription_the_api_key_path_is_unchanged(monkeypatch) -> None:
    _patch_repos(monkeypatch, cred=_api_cred(), settings={})

    built = await build_anthropic_env(AsyncMock())

    assert built.source == "api_key"
    assert built.env["CLAUDE_CODE_OAUTH_TOKEN"] == ""
