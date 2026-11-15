"""Agent 会话装配用例默认带一条假的生效连线：没有连线时装配会拒绝启动（见 ``AgentConnectionMissing``）。

要验证「没有连线」或读真实凭证的用例，自己再调 ``use_provider_env`` 覆盖。
"""

import pytest

from tests.fakes import connected_provider_env, use_provider_env


@pytest.fixture(autouse=True)
def _agent_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    use_provider_env(monkeypatch, connected_provider_env)
