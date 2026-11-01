from filbert.extract.domtext import parse
from filbert.meta.head import extract_head, parse_robots, split_keywords
from tests.conftest import fixture_html

BASE = "https://news.example.ir/economy/123456/?utm_source=x"


def test_news_fixture_head() -> None:
    seo = extract_head(parse(fixture_html("news.html")), BASE)
    assert seo.title == "افزایش قیمت بیت‌کوین در بازار امروز - خبرگزاری نمونه"
    assert seo.title_source == "title_tag"
    assert seo.og_title == "افزایش قیمت بیت‌کوین در بازار امروز"
    assert seo.h1 == "افزایش قیمت بیت‌کوین در بازار امروز"
    assert seo.description.startswith("بیت‌کوین امروز") and seo.description_source == "meta"
    assert seo.keywords == ["بیت‌کوین", "ارز دیجیتال", "بازار"] and seo.keywords_source == "meta"
    assert (
        seo.canonical == "https://news.example.ir/economy/123456/"
        and seo.canonical_source == "link_canonical"
    )
    assert seo.robots.raw == "index, follow, max-snippet:-1"
    assert not seo.robots.noindex and not seo.robots.nofollow
    assert seo.lang_declared == "fa" and seo.lang_source == "html_lang"
    assert seo.open_graph["og:description"] == "توضیح OG"
    assert seo.twitter == {}


def test_priority_chain_fallbacks() -> None:
    html = """<html><head>
      <meta property="og:title" content="  OG   عنوان ">
      <meta property="og:description" content="OG توضیح">
      <meta property="og:url" content="/canon/">
      <meta property="og:locale" content="fa_IR">
      <meta property="article:tag" content="الف"><meta property="article:tag" content="ب">
      <meta name="twitter:card" content="summary">
    </head><body><h1>تیتر</h1></body></html>"""
    seo = extract_head(parse(html), "https://a.ir/x/")
    assert seo.title == "OG عنوان" and seo.title_source == "og_title" and seo.title_tag is None
    assert seo.description == "OG توضیح" and seo.description_source == "og_description"
    assert seo.keywords == ["الف", "ب"] and seo.keywords_source == "article_tag"
    assert seo.canonical == "https://a.ir/canon/" and seo.canonical_source == "og_url"
    assert seo.lang_declared == "fa" and seo.lang_source == "og_locale"
    assert seo.twitter == {"twitter:card": "summary"}


def test_h1_as_last_title_resort_and_nulls() -> None:
    seo = extract_head(parse("<html><body><h1>فقط  تیتر</h1></body></html>"), "https://a.ir/")
    assert seo.title == "فقط تیتر" and seo.title_source == "h1"
    assert seo.description is None and seo.description_source is None
    assert seo.keywords is None and seo.canonical is None and seo.lang_declared is None
    assert seo.robots.raw is None


def test_robots_sources() -> None:
    html = '<html><head><meta name="robots" content="noindex"><meta name="googlebot" content="nofollow"></head></html>'
    seo = extract_head(parse(html), "https://a.ir/", {"X-Robots-Tag": "noarchive"})
    assert seo.robots.noindex and seo.robots.nofollow
    assert seo.robots.raw == "noindex, nofollow, noarchive"
    assert parse_robots("none").noindex and parse_robots("none").nofollow
    assert parse_robots(None).raw is None


def test_keywords_split_persian_and_english_commas() -> None:
    assert split_keywords("الف، ب, ج ؛ د;") == ["الف", "ب", "ج", "د"]
    assert split_keywords("  ") is None


def test_hreflang() -> None:
    html = """<html><head>
      <link rel="alternate" hreflang="en" href="/en/">
      <link rel="alternate" hreflang="x-default" href="https://a.ir/">
      <link rel="alternate" type="application/rss+xml" href="/feed">
    </head></html>"""
    seo = extract_head(parse(html), "https://a.ir/fa/")
    assert [(h.lang, h.url) for h in seo.hreflang] == [
        ("en", "https://a.ir/en/"),
        ("x-default", "https://a.ir/"),
    ]


def test_metadata_not_normalized() -> None:
    html = '<html><head><title>كيف پول</title><meta name="description" content="٠١٢"></head></html>'
    seo = extract_head(parse(html), "https://a.ir/")
    assert seo.title == "كيف پول"  # ي/ك عربی دست نخورده
    assert seo.description == "٠١٢"
