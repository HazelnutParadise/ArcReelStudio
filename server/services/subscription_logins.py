"""网页上的订阅登录：开始登录、贴验证码（Claude）、轮询结果（ChatGPT、Grok device code），完成后存成连线。

登录完成时（不论页面是否还在轮询）立即建立或更新 ``provider_credential``，结果保留到过期，页面断线重连也查得到。
同一账号（以账号说明比对）重新登录时更新原连线，不另建一条，免得两条连线各自刷新同一账号的令牌。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lib.config.registry import PROVIDER_REGISTRY, LoginKind
from lib.db.repositories.credential_repository import CredentialRepository
from lib.subscriptions.claude_login import ClaudeLoginError, ClaudeLoginManager
from lib.subscriptions.codex_login import CodexLoginManager
from lib.subscriptions.connection_home import HOME_BASED_PROVIDERS, install_credentials
from lib.subscriptions.device_login import DeviceLoginResult, SubscriptionLoginError
from lib.subscriptions.grok_login import GrokLoginManager

logger = logging.getLogger(__name__)

#: 登录记录（含结果）保留多久
RECORD_TTL_SECONDS = 20 * 60
POLL_INTERVAL_SECONDS = 1.0

LoginState = Literal["pending", "succeeded", "failed"]


class DeviceLoginManager(Protocol):
    async def start(self) -> tuple[str, str, str]: ...
    async def status(self, login_id: str) -> DeviceLoginResult: ...
    async def cancel(self, login_id: str) -> None: ...
    async def close(self) -> None: ...


class SubscriptionLoginServiceError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass
class LoginRecord:
    login_id: str
    provider_id: str
    kind: LoginKind
    url: str
    user_code: str | None
    expires_at: datetime
    driver_login_id: str
    state: LoginState = "pending"
    credential_id: int | None = None
    error_code: str | None = None
    created: float = field(default_factory=time.monotonic)
    watcher: asyncio.Task[None] | None = None


class SubscriptionLoginService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        claude: ClaudeLoginManager | None = None,
        device_managers: dict[str, DeviceLoginManager] | None = None,
        on_credentials_changed: Callable[[], None] | None = None,
        poll_interval: float = POLL_INTERVAL_SECONDS,
        record_ttl: float = RECORD_TTL_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._claude = claude or ClaudeLoginManager()
        self._device: dict[str, DeviceLoginManager] = device_managers or {
            "chatgpt-subscription": CodexLoginManager(),
            "grok-subscription": GrokLoginManager(),
        }
        self._on_changed = on_credentials_changed
        self._poll_interval = poll_interval
        self._record_ttl = record_ttl
        self._records: dict[str, LoginRecord] = {}

    async def start(self, provider_id: str) -> LoginRecord:
        meta = PROVIDER_REGISTRY.get(provider_id)
        if meta is None or meta.login_kind is None:
            raise SubscriptionLoginServiceError("provider_not_login_based")
        self._sweep()
        ttl = self._record_ttl
        if meta.login_kind == "code_paste":
            try:
                driver_id, url = await self._claude.start()
            except ClaudeLoginError as exc:
                raise SubscriptionLoginServiceError(exc.code, exc.detail) from exc
            record = self._new_record(provider_id, "code_paste", url, None, driver_id, ttl)
        else:
            manager = self._device.get(provider_id)
            if manager is None:
                raise SubscriptionLoginServiceError("provider_not_login_based")
            try:
                driver_id, url, code = await manager.start()
            except SubscriptionLoginError as exc:
                raise SubscriptionLoginServiceError(exc.code, exc.detail) from exc
            record = self._new_record(provider_id, "device_code", url, code, driver_id, ttl)
            record.watcher = asyncio.create_task(self._watch(record, manager), name=f"subscription-login-{provider_id}")
        self._records[record.login_id] = record
        return record

    def get(self, provider_id: str, login_id: str) -> LoginRecord:
        self._sweep()
        record = self._records.get(login_id)
        if record is None or record.provider_id != provider_id:
            raise SubscriptionLoginServiceError("login_not_found")
        return record

    async def submit_code(self, provider_id: str, login_id: str, code: str) -> LoginRecord:
        record = self.get(provider_id, login_id)
        if record.kind != "code_paste":
            raise SubscriptionLoginServiceError("login_not_found")
        if record.state != "pending":
            return record
        try:
            token = await self._claude.submit_code(record.driver_login_id, code)
        except ClaudeLoginError as exc:
            if exc.code in ("invalid_code",):
                raise SubscriptionLoginServiceError(exc.code, exc.detail) from exc
            record.state, record.error_code = "failed", exc.code
            return record
        record.credential_id = await self._save(provider_id, token, account_label=None)
        record.state = "succeeded"
        return record

    async def cancel(self, provider_id: str, login_id: str) -> None:
        record = self._records.pop(login_id, None)
        if record is None or record.provider_id != provider_id:
            return
        if record.watcher is not None and not record.watcher.done():
            record.watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await record.watcher
        if record.state == "pending":
            if record.kind == "code_paste":
                await self._claude.cancel(record.driver_login_id)
            elif manager := self._device.get(provider_id):
                await manager.cancel(record.driver_login_id)

    async def close(self) -> None:
        for record in list(self._records.values()):
            await self.cancel(record.provider_id, record.login_id)
        await self._claude.close()
        for manager in self._device.values():
            await manager.close()

    def _new_record(
        self, provider_id: str, kind: LoginKind, url: str, user_code: str | None, driver_id: str, ttl: float
    ) -> LoginRecord:
        return LoginRecord(
            login_id=secrets.token_urlsafe(16),
            provider_id=provider_id,
            kind=kind,
            url=url,
            user_code=user_code,
            expires_at=datetime.fromtimestamp(time.time() + ttl, tz=UTC),
            driver_login_id=driver_id,
        )

    async def _watch(self, record: LoginRecord, manager: DeviceLoginManager) -> None:
        try:
            while True:
                result = await manager.status(record.driver_login_id)
                if result.status == "pending":
                    await asyncio.sleep(self._poll_interval)
                    continue
                if result.status == "succeeded" and result.secret:
                    record.credential_id = await self._save(
                        record.provider_id, result.secret, account_label=result.account_label
                    )
                    record.state = "succeeded"
                else:
                    record.state, record.error_code = "failed", result.error_code or "login_failed"
                return
        except SubscriptionLoginError as exc:
            record.state, record.error_code = "failed", exc.code
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("subscription login watcher failed")
            record.state, record.error_code = "failed", "login_failed"

    async def _save(self, provider_id: str, secret: str, *, account_label: str | None) -> int:
        """建立或更新连线，返回它的 id。同一账号说明的连线已存在时更新它。"""
        display = PROVIDER_REGISTRY[provider_id].display_name
        name = account_label or f"{display} {datetime.now(tz=UTC):%Y-%m-%d %H:%M}"
        stored_secret = None if provider_id in HOME_BASED_PROVIDERS else secret
        async with self._session_factory() as session:
            repo = CredentialRepository(session)
            existing = None
            if account_label:
                existing = next((c for c in await repo.list_by_provider(provider_id) if c.name == account_label), None)
            if existing is not None:
                credential_id = existing.id
                await repo.update(credential_id, api_key=stored_secret)
            else:
                created = await repo.create(provider=provider_id, name=name, api_key=stored_secret)
                credential_id = created.id
            if provider_id in HOME_BASED_PROVIDERS:
                await asyncio.to_thread(install_credentials, provider_id, credential_id, secret)
            await session.commit()
        if self._on_changed is not None:
            self._on_changed()
        return credential_id

    def _sweep(self) -> None:
        now = time.monotonic()
        for login_id, record in list(self._records.items()):
            if now - record.created > self._record_ttl and (record.watcher is None or record.watcher.done()):
                self._records.pop(login_id, None)
