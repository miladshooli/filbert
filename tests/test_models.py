import orjson

from filbert.models import SCHEMA_VERSION, Block, PageRecord

SAMPLE = {
    "schema_version": "1.0",
    "url": "https://nobitex.ir/blog/x",
    "final_url": "https://nobitex.ir/blog/x",
    "canonical": "https://nobitex.ir/blog/x",
    "fetched_at": "2026-11-01T10:22:14+03:30",
    "http": {
        "status": 200,
        "content_type": "text/html; charset=utf-8",
        "response_ms": 412,
        "redirects": [],
        "rendered": False,
    },
    "seo": {
        "title": "عنوان",
        "title_source": "title_tag",
        "title_tag": "عنوان",
        "og_title": None,
        "h1": "عنوان",
        "description": "توضیح",
        "description_source": "meta",
        "keywords": ["الف"],
        "robots": {"raw": "index,follow", "noindex": False, "nofollow": False},
        "hreflang": [],
        "lang_declared": "fa",
        "lang_detected": "fa",
        "open_graph": {},
        "twitter": {},
        "json_ld": [],
        "json_ld_types": ["Article"],
        "author": None,
        "published_at": None,
        "modified_at": None,
    },
    "content": {
        "text": "متن می‌شود",
        "text_raw": "متن مي‌شود",
        "html": '<article lang="fa" dir="rtl"></article>',
        "markdown": "# x",
        "blocks": [
            {
                "type": "p",
                "text": "...",
                "html": "<p>...</p>",
                "xpath": "/html/body/p[1]",
                "votes": 3,
            }
        ],
        "word_count": 2,
        "char_count": 9,
        "reading_time_min": 1,
        "confidence": 0.94,
        "low_confidence": False,
        "extractors": {"readability": 0.97},
    },
    "structure": {
        "headings": [{"level": 1, "text": "x", "in_main": True}],
        "links": [
            {
                "url": "https://a.ir",
                "anchor": "a",
                "internal": True,
                "nofollow": False,
                "in_main": True,
            }
        ],
        "images": [{"src": "https://a.ir/i.png", "alt": "", "in_main": True}],
        "links_summary": {"internal": 42, "external": 7, "nofollow": 3, "in_main": 11},
        "images_summary": {"total": 9, "missing_alt": 2},
    },
    "content_hash": "a3f9",
    "raw_html_ref": "cache/raw/abc.html.zst",
}


def test_roundtrip_sample_json() -> None:
    rec = PageRecord.model_validate(SAMPLE)
    assert rec.schema_version == SCHEMA_VERSION == "1.0"
    dumped = orjson.loads(rec.model_dump_json())
    assert dumped["seo"]["title"] == "عنوان"
    assert dumped["content"]["blocks"][0]["votes"] == 3
    assert dumped["seo"]["og_title"] is None


def test_defaults_are_none_not_empty() -> None:
    rec = PageRecord(url="https://x.ir")
    assert rec.seo.title is None
    assert rec.seo.description is None
    assert rec.content.text is None
    assert rec.seo.keywords is None
    assert rec.http.status is None
    assert rec.content.blocks == []


def test_unicode_not_escaped() -> None:
    rec = PageRecord(url="https://x.ir")
    rec.content.text = "می‌شود"
    raw = orjson.dumps(rec.model_dump(mode="json"))
    assert "می‌شود".encode() in raw
    assert b"\\u" not in raw


def test_block_type_validated() -> None:
    import pytest

    with pytest.raises(ValueError):
        Block(type="span", text="", html="", xpath="")  # type: ignore[arg-type]
