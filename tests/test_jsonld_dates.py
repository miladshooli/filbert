from hypothesis import given
from hypothesis import strategies as st

from filbert.extract.domtext import parse
from filbert.meta import dates, jsonld


def test_jsonld_parse_variants() -> None:
    html = """<html><head>
    <script type="application/ld+json">{"@context":"https://schema.org","@type":"NewsArticle","headline":"تیتر","author":{"@type":"Person","name":"سارا احمدی"},"datePublished":"2026-10-31T09:00:00+03:30","keywords":"الف، ب"}</script>
    <script type="application/ld+json">[{"@type":"BreadcrumbList"},{"@type":"Organization","name":"سایت"}]</script>
    <script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"WebPage","name":"صفحه"},{"@type":["Product","Thing"],"name":"کالا"}]}</script>
    <script type="application/ld+json">{"@type":"Broken", "x": 1,}</script>
    <script type="application/ld+json">//<![CDATA[
    {"@type":"VideoObject","name":"ویدیو","uploadDate":"2026-01-02"}
    //]]></script>
    <script type="application/ld+json">not json at all</script>
    </head></html>"""
    items = jsonld.extract_jsonld(parse(html))
    types = jsonld.types_of(items)
    assert types[:3] == ["NewsArticle", "BreadcrumbList", "Organization"]
    assert {"WebPage", "Product", "Thing", "Broken", "VideoObject"} <= set(
        types
    )  # ویرگول اضافه تحمل شد
    assert jsonld.author_name(items) == "سارا احمدی"
    assert jsonld.date_published(items) == "2026-10-31T09:00:00+03:30"
    assert jsonld.headline(items) == "تیتر"
    assert jsonld.keywords(items) == ["الف", "ب"]


def test_jsonld_author_as_list_and_string() -> None:
    items = [
        {"@type": "Article", "author": ["علی", {"name": "رضا"}]},
        {"@type": "Organization", "author": "x"},
    ]
    assert jsonld.author_name(items) == "علی"
    assert (
        jsonld.author_name(
            [{"@type": "Article", "author": {"@type": "Organization", "name": "تحریریه"}}]
        )
        == "تحریریه"
    )
    assert jsonld.author_name([]) is None


def test_parse_iso_and_rfc() -> None:
    assert dates.parse_iso_or_rfc("2026-10-31T09:00:00+03:30") == "2026-10-31T09:00:00+03:30"
    assert dates.parse_iso_or_rfc("2026-10-31") == "2026-10-31"
    assert dates.parse_iso_or_rfc("2026-10-31 09:00") == "2026-10-31T09:00:00"
    assert dates.parse_iso_or_rfc("Sat, 31 Oct 2026 09:00:00 GMT") == "2026-10-31T09:00:00+00:00"
    assert dates.parse_iso_or_rfc("۲۰۲۶-۱۰-۳۱") == "2026-10-31"
    assert dates.parse_iso_or_rfc("دیروز") is None


def test_parse_jalali_text() -> None:
    assert dates.parse_text("انتشار: ۱۰ آبان ۱۴۰۵ - ۲۳:۲۵").iso == "2026-11-01T23:25:00"
    assert dates.parse_text("1405/08/10").iso == "2026-11-01"
    assert dates.parse_text("۱۴۰۵/۰۸/۱۰").calendar == "jalali"
    assert dates.parse_text("10 آبان 1405").iso == "2026-11-01"
    assert dates.parse_text("۱ فروردین ۱۴۰۰").iso == "2021-03-21"
    assert dates.parse_text("۳۰ اسفند ۱۴۰۳").iso == "2025-03-20"  # سال کبیسه شمسی
    assert (
        dates.parse_text("۳۱ اسفند ۱۴۰۴") is None
        or dates.parse_text("۳۱ اسفند ۱۴۰۴").raw != "۳۱ اسفند ۱۴۰۴"
    )


def test_parse_gregorian_text() -> None:
    assert dates.parse_text("۷ مه ۲۰۲۴").iso == "2024-05-07"
    assert dates.parse_text("Oct 30, 2003").iso == "2003-10-30"
    assert dates.parse_text("published 2026-11-01 10:22").iso == "2026-11-01T10:22:00"
    assert dates.parse_text("قیمت ۱۴۰۵۰۰ تومان") is None  # عدد بزرگ تاریخ نیست
    assert dates.parse_text("کد 13/5/1 x") is None


def test_parse_any_chain() -> None:
    p = dates.parse_any("1405/08/10", source="time")
    assert p and p.iso == "2026-11-01" and p.source == "time" and p.calendar == "jalali"
    assert dates.parse_any(None, source="x") is None


@given(st.integers(1300, 1499), st.integers(1, 12), st.integers(1, 29))
def test_jalali_roundtrip(y: int, m: int, d: int) -> None:
    import datetime as _dt

    import jdatetime

    iso = dates.jalali_to_iso(y, m, d)
    assert iso is not None
    back = jdatetime.date.fromgregorian(date=_dt.date.fromisoformat(iso))
    assert (back.year, back.month, back.day) == (y, m, d)
    month_name = next(k for k, v in dates.JALALI_MONTHS.items() if v == m)
    assert dates.parse_text(f"{d} {month_name} {y}").iso == iso
    assert dates.parse_text(f"{y}/{m:02d}/{d:02d}").iso == iso
