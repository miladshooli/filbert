import json
from pathlib import Path

from pytest_httpserver import HTTPServer
from typer.testing import CliRunner

from filbert import extract_html
from filbert.cli import app
from filbert.config import Settings
from filbert.pipeline import extract_file, fetch_and_extract
from tests.conftest import FIXTURES, fixture_html

runner = CliRunner()


def test_extract_html_news_record() -> None:
    rec = extract_html(
        fixture_html("news.html"), "https://news.example.ir/economy/123456/?utm_source=x"
    )
    assert rec.schema_version == "1.0"
    assert rec.url == "https://news.example.ir/economy/123456/"
    assert rec.canonical == "https://news.example.ir/economy/123456/"
    assert rec.seo.title_source == "title_tag"
    assert rec.content.blocks and rec.content.blocks[0].type == "h1"
    assert rec.content.html.startswith('<article lang="fa" dir="rtl">')
    assert rec.content.markdown.startswith("# افزایش قیمت بیت‌کوین")
    assert rec.content.word_count > 100 and not rec.content.low_confidence
    assert rec.content.text_raw != "" and "‌" in rec.content.text
    assert len(rec.content_hash) == 16
    assert set(rec.content.extractors) == {"readability", "cetd", "dom"}
    assert rec.content.confidence is not None and rec.content.confidence > 0.6
    assert all(b.votes >= 1 for b in rec.content.blocks)
    # متادیتا نرمال نمی‌شود، متن می‌شود
    assert rec.seo.keywords == ["بیت‌کوین", "ارز دیجیتال", "بازار"]


def test_text_normalized_but_raw_kept() -> None:
    html = "<html><body><article><p>" + "كيف پول ٠١٢ خوب است. " * 5 + "</p></article></body></html>"
    rec = extract_html(html, "https://a.ir/")
    assert "کیف پول ۰۱۲" in rec.content.text
    assert "كيف پول ٠١٢" in rec.content.text_raw


def test_low_confidence_on_short_pages() -> None:
    rec = extract_html("<html><body><p>کوتاه</p></body></html>", "https://a.ir/")
    assert rec.content.low_confidence and rec.content.word_count == 1


def test_extract_file(tmp_path: Path) -> None:
    p = tmp_path / "page.html"
    p.write_text(fixture_html("blog.html"), encoding="utf-8")
    rec = extract_file(p)
    assert rec.url.startswith("file:///")
    assert rec.http.detected_encoding == "utf-8"
    assert "کیف پول سخت‌افزاری" in rec.seo.title


async def test_fetch_and_extract_end_to_end(
    httpserver: HTTPServer, settings: Settings, tmp_path: Path
) -> None:
    httpserver.expect_request("/news").respond_with_data(
        fixture_html("news.html"), content_type="text/html; charset=utf-8"
    )
    httpserver.expect_request("/missing").respond_with_data("x", status=404)
    local = tmp_path / "blog.html"
    local.write_text(fixture_html("blog.html"), encoding="utf-8")
    out = tmp_path / "out"

    stats, records = await fetch_and_extract(
        [httpserver.url_for("/news"), httpserver.url_for("/missing"), str(local)],
        settings=settings,
        out_dir=out,
        formats=("json", "md"),
    )
    assert (stats.n, stats.ok, stats.failed) == (3, 2, 1)
    run_dir = out / stats.run_id
    assert (run_dir / "run.json").exists() and (run_dir / "errors.jsonl").read_text().count(
        "\n"
    ) == 1
    lines = (run_dir / "pages.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert len(list((run_dir / "json").glob("*.json"))) == 2 and not (run_dir / "html").exists()
    web = next(r for r in records if r.http.status == 200)
    assert (
        web.raw_html_ref
        and web.raw_html_ref.startswith("cache/raw/")
        and web.raw_html_ref.endswith(".html.zst")
    )
    assert (settings.cache_dir / "raw" / Path(web.raw_html_ref).name).exists()
    assert web.http.response_ms is not None and web.http.content_type.startswith("text/html")


def test_cli_extract_file_and_json(tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "extract",
            str(FIXTURES / "product.html"),
            "--out",
            str(out),
            "--formats",
            "json,md",
            "--json",
            "--cache-dir",
            str(tmp_path / "cache"),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["title"].startswith("خرید گوشی") and data["blocks"] >= 6
    run_dirs = list(out.iterdir())
    assert len(run_dirs) == 1 and (run_dirs[0] / "md").exists()


def test_cli_bad_format() -> None:
    result = runner.invoke(app, ["extract", "x.html", "--formats", "pdf"])
    assert result.exit_code != 0


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0 and "0.1.0" in result.output
