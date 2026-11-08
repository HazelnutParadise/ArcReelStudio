"""Agent 用哪一条 Claude 订阅连线：指定的连线优先，没指定或已不在时用默认连线，别家的连线不算。"""

from __future__ import annotations

from lib.config.repository import SystemSettingRepository
from lib.config.service import AGENT_SUBSCRIPTION_CREDENTIAL_KEY, agent_claude_subscription
from lib.db.repositories.credential_repository import CredentialRepository


async def _add(session, provider: str, name: str, token: str = "sk-ant-oat01-x"):
    return await CredentialRepository(session).create(provider=provider, name=name, api_key=token)


async def test_without_connections_there_is_no_subscription(db_session) -> None:
    assert await agent_claude_subscription(db_session) is None


async def test_the_default_connection_is_used_when_none_is_chosen(db_session) -> None:
    first = await _add(db_session, "claude-subscription", "A")
    await _add(db_session, "claude-subscription", "B")

    assert (await agent_claude_subscription(db_session)).id == first.id


async def test_a_chosen_connection_wins(db_session) -> None:
    await _add(db_session, "claude-subscription", "A")
    chosen = await _add(db_session, "claude-subscription", "B")
    await SystemSettingRepository(db_session).set(AGENT_SUBSCRIPTION_CREDENTIAL_KEY, str(chosen.id))

    assert (await agent_claude_subscription(db_session)).id == chosen.id


async def test_a_chosen_connection_that_is_gone_or_of_another_provider_falls_back(db_session) -> None:
    default = await _add(db_session, "claude-subscription", "A")
    other = await _add(db_session, "openai", "key", token="sk-x")
    settings = SystemSettingRepository(db_session)

    await settings.set(AGENT_SUBSCRIPTION_CREDENTIAL_KEY, str(other.id))
    assert (await agent_claude_subscription(db_session)).id == default.id
    await settings.set(AGENT_SUBSCRIPTION_CREDENTIAL_KEY, "999")
    assert (await agent_claude_subscription(db_session)).id == default.id
