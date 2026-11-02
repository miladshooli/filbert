import gzip
import time
from pathlib import Path

import httpx
from pytest_httpserver import HTTPServer

from filbert.config import Settings
from filbert.extract.domtext import parse
from filbert.fetch.client import Fetcher
from filbert.fetch.needs_js import needs_js
from filbert.fetch.robots import RobotsCache
from filbert.fetch.sitemap import parse_sitemap, read_url_file, urls_from_sitemap
from tests.conftest import fixture_html


def test_needs_js_static_page() -> None:
    html = fixture_html("news.html")
    v = needs_js(html, parse(html), "https://news.example.ir/x")
    assert not v.needs_js and v.visible_chars > 400


def test_needs_js_empty_shell_and_script_heavy() -> None:
    big_script = "<script>" + "x" * 60_000 + "</script>"
    html = f"<html><body><div id='__next'><noscript>فعال کنید</noscript></div>{big_script}</body></html>"
    v = needs_js(html, parse(html))
    assert v.needs_js and "empty_shell:#__next" in v.reasons and "script_heavy" in v.reasons
    assert "thin_text_large_html" in v.reasons


def test_needs_js_always_render_domain() -> None:
    html = "<html><body><p>" + "متن کافی. " * 100 + "</p></body></html>"
    assert not needs_js(html, parse(html), "https://a.ir/").needs_js
    v = needs_js(html, parse(html), "https://app.a.ir/x", always_render=frozenset({"a.ir"}))
    assert v.needs_js and v.reasons == ["always_render_domain"]


async def test_robots_allow_disallow_and_cache(httpserver: HTTPServer, tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(req):
        from werkzeug.wrappers import Response

        calls["n"] += 1
        return Response(
            "User-agent: *\nDisallow: /private/\nCrawl-delay: 2\n", content_type="text/plain"
        )

    httpserver.expect_request("/robots.txt").respond_with_handler(handler)
    rc = RobotsCache(tmp_path)
    async with httpx.AsyncClient() as client:
        assert await rc.allowed(client, httpserver.url_for("/public/x"))
        assert not await rc.allowed(client, httpserver.url_for("/private/x"))
        assert await rc.crawl_delay(client, httpserver.url_for("/")) == 2.0
    assert calls["n"] == 1  # یک بار در هر دامنه
    rc2 = RobotsCache(tmp_path)  # از دیسک
    async with httpx.AsyncClient() as client:
        assert not await rc2.allowed(client, httpserver.url_for("/private/y"))
    assert calls["n"] == 1


async def test_robots_missing_or_forbidden(httpserver: HTTPServer, tmp_path: Path) -> None:
    httpserver.expect_request("/robots.txt").respond_with_data("nope", status=404)
    rc = RobotsCache(None)
    async with httpx.AsyncClient() as client:
        assert await rc.allowed(client, httpserver.url_for("/anything"))
    rc._mem.clear()
    httpserver.clear()
    httpserver.expect_request("/robots.txt").respond_with_data("x", status=403)
    async with httpx.AsyncClient() as client:
        assert not await rc.allowed(client, httpserver.url_for("/anything"))


def test_parse_sitemap_and_url_file() -> None:
    locs, idx = parse_sitemap(
        "<urlset><url><loc> https://a.ir/x </loc></url><url><loc><![CDATA[https://a.ir/y]]></loc></url></urlset>"
    )
    assert locs == ["https://a.ir/x", "https://a.ir/y"] and not idx
    _, idx2 = parse_sitemap(
        "<sitemapindex><sitemap><loc>https://a.ir/s1.xml</loc></sitemap></sitemapindex>"
    )
    assert idx2
    assert read_url_file(["# c", " https://A.ir/p?utm_x=1 ", "", "https://a.ir/q"]) == [
        "https://a.ir/p",
        "https://a.ir/q",
    ]


async def test_urls_from_sitemap_index_gzip(httpserver: HTTPServer, settings: Settings) -> None:
    httpserver.expect_request("/sitemap.xml").respond_with_data(
        f"<sitemapindex><sitemap><loc>{httpserver.url_for('/old.xml')}</loc></sitemap><sitemap><loc>{httpserver.url_for('/new.xml.gz')}</loc></sitemap></sitemapindex>",
        content_type="application/xml",
    )
    httpserver.expect_request("/old.xml").respond_with_data(
        "<urlset><url><loc>https://a.ir/old/1</loc></url><url><loc>https://a.ir/tag/x</loc></url></urlset>",
        content_type="application/xml",
    )
    httpserver.expect_request("/new.xml.gz").respond_with_data(
        gzip.compress(
            b"<urlset><url><loc>https://a.ir/new/1</loc></url><url><loc>https://a.ir/new/1?utm_source=x</loc></url></urlset>"
        ),
        content_type="application/gzip",
    )
    async with Fetcher(settings) as f:
        urls = await urls_from_sitemap(f, httpserver.url_for("/sitemap.xml"), exclude="/tag/")
        assert urls == [
            "https://a.ir/new/1",
            "https://a.ir/old/1",
        ]  # جدیدترین sitemap اول؛ تکراری حذف
        assert await urls_from_sitemap(f, httpserver.url_for("/sitemap.xml"), limit=1) == [
            "https://a.ir/new/1"
        ]
        assert await urls_from_sitemap(f, httpserver.url_for("/sitemap.xml"), pattern=r"/old/") == [
            "https://a.ir/old/1"
        ]
    assert time.time() > 0
