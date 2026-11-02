import json
from pathlib import Path

from pytest_httpserver import HTTPServer
from typer.testing import CliRunner

from filbert.cli import app
from filbert.config import Settings
from filbert.pipeline import fetch_and_extract
from tests.conftest import fixture_html

runner = CliRunner()
NEWS = fixture_html("news.html")


async def test_robots_blocks_and_only_changed(
    httpserver: HTTPServer, settings: Settings, tmp_path: Path
) -> None:
    httpserver.expect_request("/robots.txt").respond_with_data(
        "User-agent: *\nDisallow: /private/\n", content_type="text/plain"
    )
    httpserver.expect_request("/private/p").respond_with_data(NEWS, content_type="text/html")
    httpserver.expect_request("/news").respond_with_data(NEWS, content_type="text/html")
    s = settings.model_copy(update={"respect_robots": True, "workers": 1})
    out = tmp_path / "out"
    stats, recs = await fetch_and_extract(
        [httpserver.url_for("/private/p"), httpserver.url_for("/news")], settings=s, out_dir=out
    )
    assert stats.robots_blocked == 1 and stats.ok == 1 and stats.failed == 1
    # اجرای دوم با only_changed: محتوا تغییری نکرده → نوشته نمی‌شود
    stats2, _ = await fetch_and_extract(
        [httpserver.url_for("/news")], settings=s, out_dir=out, only_changed=True, force=True
    )
    assert stats2.skipped_unchanged == 1 and stats2.ok == 0
    run_dir = out / stats2.run_id
    assert (run_dir / "pages.jsonl").read_text() == ""
    assert json.loads((run_dir / "run.json").read_bytes())["skipped_unchanged"] == 1


async def test_process_pool_path(
    httpserver: HTTPServer, settings: Settings, tmp_path: Path
) -> None:
    for i in range(5):
        httpserver.expect_request(f"/n{i}").respond_with_data(
            NEWS.replace("افزایش قیمت", f"خبر {i} افزایش قیمت"), content_type="text/html"
        )
    s = settings.model_copy(update={"respect_robots": False, "workers": 2})
    stats, recs = await fetch_and_extract(
        [httpserver.url_for(f"/n{i}") for i in range(5)], settings=s, out_dir=tmp_path / "out"
    )
    assert stats.ok == 5 and len({r.content_hash for r in recs}) == 5
    assert all(r.seo.author == "سارا احمدی" for r in recs)


async def test_render_auto_with_fake_pool(
    httpserver: HTTPServer, settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    shell = "<html><body><div id='__next'></div><script>" + "x" * 60000 + "</script></body></html>"
    httpserver.expect_request("/spa").respond_with_data(shell, content_type="text/html")

    class FakePool:
        stats = {"ok": 0}

        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def render(self, url):
            from filbert.fetch.render import RenderResult

            self.stats["ok"] += 1
            return RenderResult(url=url, final_url=url, status=200, html=NEWS, ms=5)

    import filbert.fetch.render as render_mod

    monkeypatch.setattr(render_mod, "RenderPool", FakePool)
    s = settings.model_copy(update={"respect_robots": False, "workers": 1, "render": "auto"})
    stats, recs = await fetch_and_extract(
        [httpserver.url_for("/spa")], settings=s, out_dir=tmp_path / "out"
    )
    assert (
        stats.rendered == 1
        and recs[0].http.rendered
        and recs[0].seo.title.startswith("افزایش قیمت")
    )
    assert stats.settings["render_stats"]["ok"] == 1
    # نسخه رندرشده در کش ذخیره شد
    from filbert.fetch.cache import Cache

    c = Cache(s.cache_dir)
    e = c.lookup(recs[0].url)
    assert e is not None and e.rendered
    c.close()


def test_cli_crawl_from_urls_file(tmp_path: Path, httpserver: HTTPServer) -> None:
    httpserver.expect_request("/a").respond_with_data(NEWS, content_type="text/html")
    httpserver.expect_request("/b").respond_with_data(NEWS, content_type="text/html")
    f = tmp_path / "urls.txt"
    f.write_text(
        f"# list\n{httpserver.url_for('/a')}\n{httpserver.url_for('/b')}\n", encoding="utf-8"
    )
    result = runner.invoke(
        app,
        [
            "crawl",
            "--urls",
            str(f),
            "--out",
            str(tmp_path / "out"),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--ignore-robots",
            "--workers",
            "1",
            "--formats",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "ok=2" in result.output


def test_cli_crawl_requires_source() -> None:
    assert runner.invoke(app, ["crawl"]).exit_code != 0
