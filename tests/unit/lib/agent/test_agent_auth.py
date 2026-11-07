"""Agent 认证来源选择：订阅、API Key 与额度用完后的切换。"""

from __future__ import annotations

import pytest

from lib.agent.agent_auth import (
    DEFAULT_AUTH_MODE,
    AuthAvailability,
    choose_auth_source,
    fallback_source,
    parse_auth_mode,
)


@pytest.fixture
def availability() -> AuthAvailability:
    return AuthAvailability()


def test_unknown_or_empty_mode_falls_back_to_the_default() -> None:
    assert parse_auth_mode("") == DEFAULT_AUTH_MODE
    assert parse_auth_mode("whatever") == DEFAULT_AUTH_MODE
    assert parse_auth_mode("subscription") == "subscription"


def test_the_default_prefers_the_subscription() -> None:
    assert DEFAULT_AUTH_MODE == "prefer_subscription"


@pytest.mark.parametrize(
    ("mode", "has_api_key", "has_subscription", "expected"),
    [
        ("api_key", True, True, "api_key"),
        ("subscription", True, True, "subscription"),
        ("prefer_subscription", True, True, "subscription"),
        ("prefer_subscription", True, False, "api_key"),
        ("prefer_api_key", True, True, "api_key"),
        ("prefer_api_key", False, True, "subscription"),
        # 什么都没配：照旧走 API Key 路径（回落到系统设置），由 CLI 报出缺少凭证
        ("prefer_subscription", False, False, "api_key"),
    ],
)
def test_choose_follows_the_mode_and_what_is_configured(
    availability, mode, has_api_key, has_subscription, expected
) -> None:
    assert (
        choose_auth_source(
            mode, has_api_key=has_api_key, has_subscription=has_subscription, availability=availability, now=0
        )
        == expected
    )


def test_an_exhausted_subscription_switches_preferred_mode_to_the_api_key(availability) -> None:
    availability.mark_unavailable("subscription", until=100)

    assert (
        choose_auth_source(
            "prefer_subscription", has_api_key=True, has_subscription=True, availability=availability, now=50
        )
        == "api_key"
    )
    # 重置时间过了就回到订阅
    assert (
        choose_auth_source(
            "prefer_subscription", has_api_key=True, has_subscription=True, availability=availability, now=150
        )
        == "subscription"
    )


def test_an_exhausted_api_key_switches_preferred_mode_to_the_subscription(availability) -> None:
    availability.mark_unavailable("api_key", until=100)

    assert (
        choose_auth_source("prefer_api_key", has_api_key=True, has_subscription=True, availability=availability, now=0)
        == "subscription"
    )


def test_only_modes_never_switch(availability) -> None:
    availability.mark_unavailable("subscription", until=100)
    availability.mark_unavailable("api_key", until=100)

    assert (
        choose_auth_source("subscription", has_api_key=True, has_subscription=True, availability=availability, now=0)
        == "subscription"
    )
    assert (
        choose_auth_source("api_key", has_api_key=True, has_subscription=True, availability=availability, now=0)
        == "api_key"
    )


def test_both_exhausted_keeps_the_preferred_source(availability) -> None:
    availability.mark_unavailable("subscription", until=100)
    availability.mark_unavailable("api_key", until=100)

    assert (
        choose_auth_source(
            "prefer_subscription", has_api_key=True, has_subscription=True, availability=availability, now=0
        )
        == "subscription"
    )


def test_a_new_login_clears_the_subscription_mark(availability) -> None:
    availability.mark_unavailable("subscription", until=None)
    assert availability.unavailable_until("subscription", now=10**12) is not None

    availability.clear("subscription")

    assert availability.unavailable_until("subscription", now=0) is None


def test_fallback_source_only_exists_for_preferred_modes_with_the_other_side_configured() -> None:
    assert fallback_source("prefer_subscription", "subscription", has_api_key=True, has_subscription=True) == "api_key"
    assert fallback_source("prefer_api_key", "api_key", has_api_key=True, has_subscription=True) == "subscription"
    assert fallback_source("prefer_subscription", "subscription", has_api_key=False, has_subscription=True) is None
    assert fallback_source("subscription", "subscription", has_api_key=True, has_subscription=True) is None
    assert fallback_source("api_key", "api_key", has_api_key=True, has_subscription=True) is None
