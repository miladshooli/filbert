import asyncio
import socket
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer

from filbert.config import Settings
from filbert.fetch.client import Fetcher, FetchError
from filbert.fetch.guard import URLGuard, URLNotAllowed
from tests.conftest import fixture_html


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost:8000/x",
        "http://10.0.0.5/",
        "http://192.168.1.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0/",
        "http://printer.local/",
        "http://db.internal/",
        "file:///etc/passwd",
        "gopher://example.com/",
        "http:///nohost",
    ],
)
async def test_guard_blocks_private_and_odd_urls(url: str) -> None:
    with pytest.raises(URLNotAllowed):
        await URLGuard().check(url)


async def test_guard_allows_public_ip_literal() -> None:
    await URLGuard().check("https://1.1.1.1/")


async def test_guard_resolves_names(monkeypatch) -> None:
    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(host, port, **kw):
        ip = {"evil.example": "10.1.2.3", "good.example": "93.184.216.34"}[host]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    g = URLGuard()
    await g.check("https://good.example/post")
    with pytest.raises(URLNotAllowed, match="private address 10.1.2.3"):
        await g.check("https://evil.example/")
    assert await g.allows("https://good.example/") and not await g.allows("https://evil.example/")


async def test_guard_allow_private_still_checks_scheme() -> None:
    g = URLGuard(allow_private=True)
    await g.check("http://127.0.0.1/")
    with pytest.raises(URLNotAllowed):
        await g.check("ftp://127.0.0.1/")


class _PathGuard(URLGuard):
    """شبیه‌سازی مقصد داخلی روی سرور تست: هر مسیری با `/internal` ممنوع است."""

    async def check(self, url: str) -> None:
        if "/internal" in url:
            raise URLNotAllowed("internal target")


async def test_fetcher_blocks_redirect_to_private_target(
    httpserver: HTTPServer, settings: Settings
) -> None:
    httpserver.expect_request("/start").respond_with_data(
        "", status=302, headers={"Location": httpserver.url_for("/internal/secret")}
    )
    httpserver.expect_request("/internal/secret").respond_with_data("secret")
    async with Fetcher(settings, guard=_PathGuard()) as f:
        with pytest.raises(FetchError) as ei:
            await f.fetch(httpserver.url_for("/start"))
    assert ei.value.blocked and "internal target" in ei.value.reason
    # فقط یک درخواست زده شد؛ مقصد داخلی هرگز دریافت نشد و retry هم نشد
    assert [r.path for r, _ in httpserver.log] == ["/start"]


async def test_fetcher_block_private_setting(httpserver: HTTPServer, settings: Settings) -> None:
    httpserver.expect_request("/p").respond_with_data("x")
    s = settings.model_copy(update={"block_private_urls": True})
    async with Fetcher(s) as f:
        with pytest.raises(FetchError) as ei:
            await f.fetch(httpserver.url_for("/p"))
    assert ei.value.blocked and not httpserver.log


async def test_fetcher_body_cap(httpserver: HTTPServer, settings: Settings, tmp_path: Path) -> None:
    big = fixture_html("news.html") * 50
    httpserver.expect_request("/big").respond_with_data(big, content_type="text/html")
    s = settings.model_copy(update={"max_body_bytes": 10_000})
    async with Fetcher(s) as f:
        with pytest.raises(FetchError, match="body too large"):
            await f.fetch(httpserver.url_for("/big"))
        ok = await Fetcher(settings).__aenter__()
        try:
            r = await ok.fetch(httpserver.url_for("/big"))
        finally:
            await ok.__aexit__(None, None, None)
    assert len(r.body) == len(big.encode("utf-8"))
