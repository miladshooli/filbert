import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from filbert.models import Block, PageRecord, RunStats
from filbert.out import html_writer, json_writer, md_writer
from filbert.out.store import Store, slugify_url


def sample() -> PageRecord:
    rec = PageRecord(url="https://nobitex.ir/blog/x/", final_url="https://nobitex.ir/blog/x/")
    rec.fetched_at = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    rec.seo.title = "عنوان می‌شود"
    rec.seo.description = "توضیح"
    rec.seo.lang_declared = "fa"
    rec.content.blocks = [
        Block(
            type="h1",
            text="عنوان می‌شود",
            html='<h1 dir="auto">عنوان می‌شود</h1>',
            xpath="/html/body/h1[1]",
        ),
        Block(
            type="p",
            text="متن",
            html='<p dir="auto">متن <strong>مهم</strong></p>',
            xpath="/html/body/p[1]",
        ),
        Block(
            type="table",
            text="الف ب",
            xpath="/html/body/table[1]",
            html='<table dir="auto"><tr><th>الف</th><th>ب</th></tr><tr><td>۱</td><td>۲</td></tr></table>',
        ),
        Block(
            type="table",
            text="چند خط",
            xpath="/html/body/table[2]",
            html='<table dir="auto"><tr><td>چند<br>خط</td></tr></table>',
        ),
    ]
    rec.content.html = (
        '<article lang="fa" dir="rtl">\n'
        + "\n".join(b.html for b in rec.content.blocks)
        + "\n</article>"
    )
    rec.content.word_count = 5
    return rec


def test_json_unicode_unescaped() -> None:
    raw = json_writer.dumps(sample())
    assert "می‌شود".encode() in raw and b"\\u" not in raw
    data = json.loads(raw)
    assert data["schema_version"] == "1.0" and data["seo"]["og_title"] is None


def test_html_document() -> None:
    out = html_writer.render(sample())
    assert out.startswith('<!doctype html>\n<html lang="fa" dir="rtl">')
    assert "<title>عنوان می‌شود</title>" in out
    assert '<article lang="fa" dir="rtl">' in out
    assert 'data-source-url="https://nobitex.ir/blog/x/"' in out
    assert "<style" not in out and "<script" not in out


def test_markdown_front_matter_and_body() -> None:
    out = md_writer.render(sample())
    assert out.startswith("---\ntitle: عنوان می‌شود\nurl: https://nobitex.ir/blog/x/\n")
    assert "dir: rtl" in out and "word_count: 5" in out
    body = out.split("---\n", 2)[2]
    assert "# عنوان می‌شود" in body
    assert "متن **مهم**" in body
    assert "| الف | ب |" in body  # جدول ساده → pipe table
    assert "<table" in body and "چند<br>خط" in body  # جدول چندخطی → HTML خام
    assert "‌" in body


@pytest.mark.parametrize(
    ("url", "prefix"),
    [
        ("https://nobitex.ir/blog/post-1/", "nobitex.ir-blog-post-1"),
        (
            "https://fa.wikipedia.org/wiki/%D8%AA%D9%87%D8%B1%D8%A7%D9%86",
            "fa.wikipedia.org-wiki-تهران",
        ),
        ("https://a.ir/x?q=1&b=2", "a.ir-x-q-1-b-2"),
        ('https://a.ir/bad:"<>|?*name', "a.ir-bad-name"),
        ("https://a.ir/", "a.ir"),
    ],
)
def test_slug(url: str, prefix: str) -> None:
    slug = slugify_url(url)
    assert slug.startswith(prefix), slug
    assert len(slug) <= 129
    assert not any(c in slug for c in '<>:"/\\|?* ')


def test_slug_length_and_uniqueness() -> None:
    a = slugify_url("https://a.ir/" + "x" * 300)
    b = slugify_url("https://a.ir/" + "x" * 301)
    assert len(a) == 129 and a != b


def test_store_layout(tmp_path: Path) -> None:
    store = Store(tmp_path / "out", run_id="r1")
    rec = sample()
    paths = store.write(rec)
    store.write_error("https://a.ir/bad", "http 404", 404)
    stats = RunStats(
        run_id="r1", tool_version="0.1.0", started_at=datetime.now(UTC), n=2, ok=1, failed=1
    )
    run_json = store.finish(stats)
    root = tmp_path / "out" / "r1"
    assert set(paths) == {"json", "html", "md"}
    assert all(p.exists() and p.parent.parent == root for p in paths.values())
    lines = (root / "pages.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["url"] == rec.url
    err = json.loads((root / "errors.jsonl").read_text(encoding="utf-8"))
    assert err["status"] == 404
    assert json.loads(run_json.read_bytes())["ok"] == 1


def test_store_formats_subset(tmp_path: Path) -> None:
    store = Store(tmp_path, run_id="r2", formats=("md",))
    paths = store.write(sample())
    assert set(paths) == {"md"} and not (tmp_path / "r2" / "json").exists()
    store.close()
    with pytest.raises(ValueError):
        Store(tmp_path, formats=("pdf",))
