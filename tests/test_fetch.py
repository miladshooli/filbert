import time

import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Request, Response

from filbert.config import Settings
from filbert.fetch.cache import Cache, raw_key_for
from filbert.fetch.client import Fetcher, FetchError, detect_encoding

FA_HTML = "<!doctype html><html lang='fa'><head><title>سلام</title></head><body><p>می‌شود</p></body></html>"


async def test_200_and_cache_store(
    httpserver: HTTPServer, settings: Settings, cache: Cache
) -> None:
    httpserver.expect_request("/p").respond_with_data(
        FA_HTML, content_type="text/html; charset=utf-8", headers={"ETag": '"v1"'}
    )
    url = httpserver.url_for("/p?utm_source=x")
    async with Fetcher(settings, cache) as f:
        r = await f.fetch(url)
    assert r.status == 200
    assert r.url.endswith("/p")  # utm حذف شده
    assert "می‌شود" in r.text
    assert r.encoding == "utf-8"
    assert not r.from_cache
    e = cache.lookup(r.url)
    assert e is not None and e.etag == '"v1"' and e.raw_key == raw_key_for(r.url)
    assert cache.raw.get(e.raw_key) == FA_HTML.encode()


async def test_304_served_from_cache(
    httpserver: HTTPServer, settings: Settings, cache: Cache
) -> None:
    seen: list[dict] = []

    def handler(req: Request) -> Response:
        seen.append(dict(req.headers))
        if req.headers.get("If-None-Match") == '"v1"':
            return Response(status=304)
        return Response(FA_HTML, content_type="text/html; charset=utf-8", headers={"ETag": '"v1"'})

    httpserver.expect_request("/p").respond_with_handler(handler)
    url = httpserver.url_for("/p")
    async with Fetcher(settings, cache) as f:
        r1 = await f.fetch(url)
        r2 = await f.fetch(url)
    assert not r1.from_cache
    assert r2.from_cache and r2.not_modified
    assert r2.status == 200  # وضعیت اصلی کش‌شده
    assert r2.text == r1.text
    assert seen[1]["If-None-Match"] == '"v1"'


async def test_redirect_chain(httpserver: HTTPServer, settings: Settings, cache: Cache) -> None:
    httpserver.expect_request("/old").respond_with_data(
        "", status=301, headers={"Location": httpserver.url_for("/new")}
    )
    httpserver.expect_request("/new").respond_with_data(FA_HTML, content_type="text/html")
    async with Fetcher(settings, cache) as f:
        r = await f.fetch(httpserver.url_for("/old"))
    assert r.status == 200
    assert r.final_url.endswith("/new")
    assert len(r.redirects) == 1 and r.redirects[0].endswith("/old")


async def test_429_then_success(httpserver: HTTPServer, settings: Settings) -> None:
    calls = {"n": 0}

    def handler(req: Request) -> Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return Response("slow down", status=429, headers={"Retry-After": "0"})
        return Response(FA_HTML, content_type="text/html")

    httpserver.expect_request("/r").respond_with_handler(handler)
    async with Fetcher(settings) as f:
        r = await f.fetch(httpserver.url_for("/r"))
    assert r.status == 200 and r.attempts == 3 and calls["n"] == 3


async def test_5xx_exhausts_retries(httpserver: HTTPServer, settings: Settings) -> None:
    httpserver.expect_request("/bad").respond_with_data("x", status=503)
    async with Fetcher(settings) as f:
        with pytest.raises(FetchError) as ei:
            await f.fetch(httpserver.url_for("/bad"))
    assert ei.value.status == 503


async def test_404_not_retried(httpserver: HTTPServer, settings: Settings) -> None:
    calls = {"n": 0}

    def handler(req: Request) -> Response:
        calls["n"] += 1
        return Response("nope", status=404)

    httpserver.expect_request("/nf").respond_with_handler(handler)
    async with Fetcher(settings) as f:
        with pytest.raises(FetchError) as ei:
            await f.fetch(httpserver.url_for("/nf"))
    assert ei.value.status == 404 and calls["n"] == 1


async def test_timeout_then_retry_succeeds(httpserver: HTTPServer, settings: Settings) -> None:
    calls = {"n": 0}

    def handler(req: Request) -> Response:
        calls["n"] += 1
        if calls["n"] == 1:
            time.sleep(settings.read_timeout + 0.5)
        return Response(FA_HTML, content_type="text/html")

    httpserver.expect_request("/slow").respond_with_handler(handler)
    async with Fetcher(settings) as f:
        r = await f.fetch(httpserver.url_for("/slow"))
    assert r.status == 200 and r.attempts == 2


async def test_windows_1256_header(httpserver: HTTPServer, settings: Settings) -> None:
    html = "<html><head><title>تهران</title></head><body><p>شهر زيبا</p></body></html>"
    httpserver.expect_request("/old").respond_with_data(
        html.encode("cp1256"), content_type="text/html; charset=windows-1256"
    )
    async with Fetcher(settings) as f:
        r = await f.fetch(httpserver.url_for("/old"))
    assert r.encoding == "windows-1256"
    assert "شهر زيبا" in r.text


async def test_windows_1256_meta_only(httpserver: HTTPServer, settings: Settings) -> None:
    html = (
        '<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1256">'
        "<title>تهران</title></head><body><p>شهر زيبا</p></body></html>"
    )
    httpserver.expect_request("/old2").respond_with_data(
        html.encode("cp1256"), content_type="text/html"
    )
    async with Fetcher(settings) as f:
        r = await f.fetch(httpserver.url_for("/old2"))
    assert r.encoding == "windows-1256"
    assert "شهر زيبا" in r.text


def test_detect_encoding_fallbacks() -> None:
    assert detect_encoding(b"<html></html>", "text/html; charset=UTF-8") == "utf-8"
    assert detect_encoding(b"<meta charset='utf8'>", None) == "utf-8"
    assert detect_encoding("<p>سلام دنیا، این یک متن فارسی است</p>".encode(), None) == "utf-8"
    assert detect_encoding(b"<html>", "text/html; charset=bogus-enc") == "utf-8"


async def test_per_host_limiter_spacing(httpserver: HTTPServer, settings: Settings) -> None:
    s = settings.model_copy(update={"per_host_delay_ms": 100, "per_host_concurrency": 4})
    stamps: list[float] = []

    def handler(req: Request) -> Response:
        stamps.append(time.monotonic())
        return Response(FA_HTML, content_type="text/html")

    httpserver.expect_request("/l").respond_with_handler(handler)
    async with Fetcher(s) as f:
        await f.fetch_many([httpserver.url_for(f"/l?i={i}") for i in range(3)])
    stamps.sort()
    assert all(b - a >= 0.08 for a, b in zip(stamps, stamps[1:], strict=False))
