"""订阅额度用完或认证失败：记下不可用，「优先」模式下这段连接结束、下一则消息改用另一方。"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from lib.agent.agent_auth import AuthAvailability
from server.agent_runtime import session_manager as sm_mod
from server.agent_runtime.session_actor import SessionActor
from server.agent_runtime.session_manager import ManagedSession, auth_failure_from_message
from tests.fakes import FakeSDKClient, session_state_message


def _dummy_actor() -> SessionActor:
    client = FakeSDKClient()

    @asynccontextmanager
    async def _factory():
        async with client as c:
            yield c

    return SessionActor(client_factory=_factory, on_message=lambda _m: None)


def test_a_rejected_rate_limit_event_reports_its_reset_time() -> None:
    msg = {"rate_limit_info": {"status": "rejected", "resets_at": 1_000}, "uuid": "u", "session_id": "s"}

    assert auth_failure_from_message(msg, now=10) == (True, 1_000)


def test_a_rejected_rate_limit_without_reset_time_retries_later() -> None:
    seen, until = auth_failure_from_message({"rate_limit_info": {"status": "rejected"}}, now=10)

    assert seen
    assert until is not None
    assert until > 10


def test_a_warning_is_not_a_failure() -> None:
    assert auth_failure_from_message({"rate_limit_info": {"status": "allowed_warning"}}, now=10) == (False, None)


def test_an_authentication_failure_waits_for_reconfiguration() -> None:
    assert auth_failure_from_message({"type": "assistant", "error": "authentication_failed"}, now=10) == (True, None)


def test_ordinary_messages_are_not_failures() -> None:
    assert auth_failure_from_message({"type": "assistant", "content": []}, now=10) == (False, None)


@pytest.fixture
def availability(monkeypatch: pytest.MonkeyPatch) -> AuthAvailability:
    fresh = AuthAvailability()
    monkeypatch.setattr(sm_mod, "auth_availability", fresh)
    return fresh


async def _run_turn(session_manager, meta_store, *, source: str, messages: list[dict]) -> ManagedSession:
    meta = await meta_store.create("demo", f"sdk-auth-{source}")
    managed = ManagedSession(
        session_id=meta.id, actor=_dummy_actor(), status="running", project_name="demo", auth_source=source
    )
    managed.resolved_sdk_id = meta.id
    session_manager.sessions[meta.id] = managed
    on_message = session_manager._make_actor_message_callback([managed])
    for message in messages:
        on_message(message)
    on_message({"type": "result", "subtype": "success", "is_error": True})
    on_message(session_state_message("idle"))
    managed._inbox.put_nowait(None)
    await session_manager._process_inbox(managed)
    return managed


class TestSubscriptionFallback:
    async def test_exhausted_subscription_closes_the_connection_when_the_api_key_can_take_over(
        self, session_manager, meta_store, availability, monkeypatch
    ):
        async def _fallback(_current):
            return "api_key"

        monkeypatch.setattr(session_manager, "_auth_fallback_for", _fallback)
        closed: list[str] = []

        async def _close(session_id, *, reason="session closed"):
            closed.append(session_id)

        monkeypatch.setattr(session_manager, "close_session", _close)

        managed = await _run_turn(
            session_manager,
            meta_store,
            source="subscription",
            messages=[{"rate_limit_info": {"status": "rejected", "resets_at": 4_000_000_000}}],
        )

        assert managed._cleanup_task is not None
        await managed._cleanup_task
        assert not availability.is_available("subscription")
        assert closed == [managed.session_id]

    async def test_without_a_fallback_the_connection_stays(
        self, session_manager, meta_store, availability, monkeypatch
    ):
        async def _no_fallback(_current):
            return None

        monkeypatch.setattr(session_manager, "_auth_fallback_for", _no_fallback)
        closed: list[str] = []

        async def _close(session_id, *, reason="session closed"):
            closed.append(session_id)

        monkeypatch.setattr(session_manager, "close_session", _close)

        await _run_turn(
            session_manager,
            meta_store,
            source="subscription",
            messages=[{"type": "assistant", "error": "rate_limit", "content": [], "parent_tool_use_id": None}],
        )

        # 标记照样记下（「只用订阅」时设置页也要看得到额度用完），但连接不动
        assert not availability.is_available("subscription")
        assert closed == []

    async def test_a_normal_turn_marks_nothing(self, session_manager, meta_store, availability, monkeypatch):
        async def _unexpected(_current):
            raise AssertionError("没有失败时不该查改用哪一方")

        monkeypatch.setattr(session_manager, "_auth_fallback_for", _unexpected)

        await _run_turn(session_manager, meta_store, source="subscription", messages=[])

        assert availability.is_available("subscription")
