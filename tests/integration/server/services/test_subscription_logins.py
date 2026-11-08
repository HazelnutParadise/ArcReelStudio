"""订阅登录服务：登录完成就存成连线（不靠页面轮询），同一账号重新登录时更新原连线，凭证落在对的地方。"""

from __future__ import annotations

import asyncio
import json

import pytest

from lib.db.repositories.credential_repository import CredentialRepository
from lib.infra.data_root_layout import DataRootLayout
from lib.subscriptions.device_login import DeviceLoginResult
from server.services.subscription_logins import SubscriptionLoginService, SubscriptionLoginServiceError
from tests.subscription_fakes import FakeClaude, FakeDevice

AUTH_JSON = json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "a"}})


def _service(session_factory, *, device: FakeDevice | None = None, changed: list[int] | None = None):
    return SubscriptionLoginService(
        session_factory,
        claude=FakeClaude(),  # type: ignore[arg-type]
        device_managers={"chatgpt-subscription": device or FakeDevice(DeviceLoginResult(status="pending"))},
        on_credentials_changed=(lambda: changed.append(1)) if changed is not None else None,
        poll_interval=0.01,
    )


async def _until_done(service: SubscriptionLoginService, provider_id: str, login_id: str):
    for _ in range(300):
        record = service.get(provider_id, login_id)
        if record.state != "pending":
            return record
        await asyncio.sleep(0.01)
    raise AssertionError("login never finished")


async def test_a_device_login_is_saved_as_a_connection_without_anyone_polling(session_factory) -> None:
    device = FakeDevice(DeviceLoginResult(status="succeeded", secret=AUTH_JSON, account_label="me@x.com (plus)"))
    changed: list[int] = []
    service = _service(session_factory, device=device, changed=changed)

    record = await service.start("chatgpt-subscription")
    assert (record.kind, record.url, record.user_code) == ("device_code", "https://auth.example/device", "ABCD-1234")
    device.release.set()
    done = await _until_done(service, "chatgpt-subscription", record.login_id)

    assert done.state == "succeeded"
    async with session_factory() as session:
        cred = await CredentialRepository(session).get_by_id(done.credential_id)
    assert cred is not None
    assert (cred.provider, cred.name, cred.api_key, cred.is_active) == (
        "chatgpt-subscription",
        "me@x.com (plus)",
        None,
        True,
    )
    home = DataRootLayout.current().subscription_home("chatgpt-subscription", cred.id)
    assert (home / "auth.json").read_text(encoding="utf-8") == AUTH_JSON
    assert changed == [1]
    # 结果保留到过期，页面再问一次仍看得到
    assert service.get("chatgpt-subscription", record.login_id).state == "succeeded"


async def test_logging_in_to_the_same_account_again_updates_that_connection(session_factory) -> None:
    device = FakeDevice(DeviceLoginResult(status="succeeded", secret=AUTH_JSON, account_label="me@x.com (plus)"))
    service = _service(session_factory, device=device)
    device.release.set()

    first = await _until_done(service, "chatgpt-subscription", (await service.start("chatgpt-subscription")).login_id)
    device.result = DeviceLoginResult(status="succeeded", secret='{"new": 1}', account_label="me@x.com (plus)")
    second = await _until_done(service, "chatgpt-subscription", (await service.start("chatgpt-subscription")).login_id)

    assert first.credential_id == second.credential_id
    async with session_factory() as session:
        assert len(await CredentialRepository(session).list_by_provider("chatgpt-subscription")) == 1
    home = DataRootLayout.current().subscription_home("chatgpt-subscription", second.credential_id)
    assert (home / "auth.json").read_text(encoding="utf-8") == '{"new": 1}'


async def test_a_failed_device_login_saves_nothing(session_factory) -> None:
    device = FakeDevice(DeviceLoginResult(status="failed", error_code="login_rejected"))
    service = _service(session_factory, device=device)
    record = await service.start("chatgpt-subscription")
    device.release.set()

    done = await _until_done(service, "chatgpt-subscription", record.login_id)

    assert (done.state, done.error_code, done.credential_id) == ("failed", "login_rejected", None)
    async with session_factory() as session:
        assert await CredentialRepository(session).list_by_provider("chatgpt-subscription") == []


async def test_a_claude_code_is_exchanged_and_the_token_stored_on_the_connection(session_factory) -> None:
    service = _service(session_factory)
    record = await service.start("claude-subscription")
    assert (record.kind, record.user_code) == ("code_paste", None)

    done = await service.submit_code("claude-subscription", record.login_id, "good")

    assert done.state == "succeeded"
    async with session_factory() as session:
        cred = await CredentialRepository(session).get_by_id(done.credential_id)
    assert cred is not None
    assert (cred.provider, cred.api_key) == ("claude-subscription", "sk-ant-oat01-token")
    assert cred.name.startswith("Claude")


async def test_a_rejected_claude_code_fails_the_login(session_factory) -> None:
    service = _service(session_factory)
    record = await service.start("claude-subscription")

    done = await service.submit_code("claude-subscription", record.login_id, "bad")

    assert (done.state, done.error_code) == ("failed", "code_rejected")


async def test_cancel_stops_the_driver_and_forgets_the_login(session_factory) -> None:
    device = FakeDevice(DeviceLoginResult(status="pending"))
    service = _service(session_factory, device=device)
    record = await service.start("chatgpt-subscription")

    await service.cancel("chatgpt-subscription", record.login_id)

    assert device.cancelled == ["driver-1"]
    with pytest.raises(SubscriptionLoginServiceError):
        service.get("chatgpt-subscription", record.login_id)


@pytest.mark.parametrize("provider_id", ["openai", "nope"])
async def test_only_subscription_providers_can_log_in(session_factory, provider_id: str) -> None:
    service = _service(session_factory)

    with pytest.raises(SubscriptionLoginServiceError) as exc:
        await service.start(provider_id)
    assert exc.value.code == "provider_not_login_based"


async def test_a_login_cannot_be_read_through_another_provider(session_factory) -> None:
    service = _service(session_factory)
    record = await service.start("claude-subscription")

    with pytest.raises(SubscriptionLoginServiceError):
        service.get("chatgpt-subscription", record.login_id)
