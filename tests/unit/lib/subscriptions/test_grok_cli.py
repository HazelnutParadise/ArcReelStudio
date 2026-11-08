"""Grok CLI 的来源：PATH 上有就用，没有时按固定版本下载并核对校验和，校验不过不装。"""

from __future__ import annotations

import gzip
import hashlib

import httpx2
import pytest

from lib.subscriptions import grok_cli

BINARY = b"#!/bin/sh\necho grok\n"
PAYLOAD = gzip.compress(BINARY)


@pytest.fixture
def linux_x86(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(grok_cli.shutil, "which", lambda _name: None)
    monkeypatch.setattr(grok_cli.platform, "system", lambda: "Linux")
    monkeypatch.setattr(grok_cli.platform, "machine", lambda: "x86_64")


def _client(payload: bytes, seen: list[str]) -> httpx2.AsyncClient:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        return httpx2.Response(200, content=payload)

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


async def test_a_grok_on_path_is_used_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(grok_cli.shutil, "which", lambda _name: "/usr/bin/grok")

    assert await grok_cli.ensure_grok_cli() == "/usr/bin/grok"


async def test_downloads_the_pinned_version_once_and_verifies_it(linux_x86, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(grok_cli.GROK_SHA256, "x86_64", hashlib.sha256(PAYLOAD).hexdigest())
    seen: list[str] = []

    async with _client(PAYLOAD, seen) as client:
        first = await grok_cli.ensure_grok_cli(client=client)
        second = await grok_cli.ensure_grok_cli(client=client)

    assert first == second == str(grok_cli.installed_grok_path())
    assert grok_cli.installed_grok_path().read_bytes() == BINARY
    assert grok_cli.installed_grok_path().stat().st_mode & 0o111
    assert seen == [f"https://x.ai/cli/grok-{grok_cli.GROK_VERSION}-linux-x86_64.gz"]


async def test_a_download_that_fails_the_checksum_is_not_installed(linux_x86) -> None:
    async with _client(PAYLOAD, []) as client:
        with pytest.raises(grok_cli.GrokCliUnavailable, match="checksum"):
            await grok_cli.ensure_grok_cli(client=client)

    assert not grok_cli.installed_grok_path().exists()


async def test_other_platforms_need_grok_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(grok_cli.shutil, "which", lambda _name: None)
    monkeypatch.setattr(grok_cli.platform, "system", lambda: "Darwin")

    with pytest.raises(grok_cli.GrokCliUnavailable, match="PATH"):
        await grok_cli.ensure_grok_cli()
