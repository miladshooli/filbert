from filbert.extract.domtext import parse
from filbert.fa.lang import detect
from filbert.meta import jsonld
from filbert.meta.social import clean_author, extract_author, extract_social
from filbert.meta.structure import collect, finalize
from tests.conftest import fixture_html

NEWS = fixture_html("news.html")


def test_social_absolute_urls() -> None:
    html = """<html><head>
    <meta property="og:title" content="ت"><meta property="og:image" content="/i.png"><meta property="og:url" content="/p/">
    <meta property="article:published_time" content="2026-10-31"><meta name="twitter:card" content="summary">
    <meta name="twitter:image" content="//cdn.a.ir/t.png"></head></html>"""
    og, tw = extract_social(parse(html), "https://a.ir/x/")
    assert og["og:image"] == "https://a.ir/i.png" and og["og:url"] == "https://a.ir/p/"
    assert og["article:published_time"] == "2026-10-31"
    assert tw == {"twitter:card": "summary", "twitter:image": "https://cdn.a.ir/t.png"}


def test_author_chain() -> None:
    t = parse(NEWS)
    assert extract_author(t, jsonld.extract_jsonld(t)) == ("سارا احمدی", "class")
    t2 = parse(
        '<html><head><meta name="author" content=" نویسنده: علی رضایی "></head><body></body></html>'
    )
    assert extract_author(t2, []) == ("علی رضایی", "meta")
    t3 = parse("<html><body><a rel='author' href='/u'>By Reza</a></body></html>")
    assert extract_author(t3, [{"@type": "Article", "author": {"name": "تحریریه"}}]) == (
        "تحریریه",
        "json_ld",
    )
    assert extract_author(t3, []) == ("Reza", "rel_author")
    assert extract_author(parse("<html><body><p>x</p></body></html>"), []) == (None, None)


def test_clean_author() -> None:
    assert clean_author("نوشته شده توسط علی") == "علی"
    assert clean_author("توسط: مریم") == "مریم"
    assert clean_author("x" * 100) is None
    assert clean_author("https://a.ir/u") is None


def test_structure_collect_and_in_main() -> None:
    t = parse(NEWS)
    page = "https://news.example.ir/economy/123456/"
    draft = collect(t, page)
    assert any(h.level == 1 and h.text.startswith("افزایش قیمت") for _, h in draft.headings)
    urls = {ln.url for _, ln in draft.links}
    assert "https://news.example.ir/economy/" in urls and "https://t.me/share?url=x" in urls
    assert any(not ln.internal for _, ln in draft.links) and any(
        ln.internal for _, ln in draft.links
    )
    assert not any("javascript" in ln.url for _, ln in draft.links)
    assert [im.src for _, im in draft.images] == ["https://news.example.ir/uploads/btc-chart.png"]
    # in_main: فقط article به‌عنوان محتوای اصلی
    art = t.css_first("article")
    st = finalize(draft, [art])
    assert st.headings[0].in_main and all(h.in_main for h in st.headings if h.level <= 2)
    assert not any(h.in_main for h in st.headings if h.text == "پربازدیدترین‌ها")
    assert st.images_summary.total == 1 and st.images_summary.missing_alt == 0
    assert st.links_summary.in_main >= 2 and st.links_summary.external >= 2
    assert st.links_summary.internal + st.links_summary.external == len(st.links)
    empty = finalize(draft, [])
    assert empty.links_summary.in_main == 0


def test_structure_lazy_images_and_sizes() -> None:
    t = parse(
        '<html><body><img data-src="/a.png" width="300px" height="x"><img src="data:image/png;base64,xx"><img src="/b.png" alt=" ب "></body></html>'
    )
    d = collect(t, "https://a.ir/")
    assert [(i.src, i.width, i.height, i.alt) for _, i in d.images] == [
        ("https://a.ir/a.png", 300, None, None),
        ("https://a.ir/b.png", None, None, "ب"),
    ]


def test_lang_detection() -> None:
    fa = "این یک متن فارسی است که برای تست تشخیص زبان نوشته شده و می‌تواند کمی طولانی‌تر باشد."
    ar = "هذا نص عربي كتب من أجل اختبار كشف اللغة ويمكن أن يكون أطول قليلاً من ذلك في النهاية."
    en = "This is an English paragraph written to test the language detector in the pipeline."
    assert detect(fa).lang == "fa"
    assert detect(ar).lang == "ar"
    assert detect(en).lang == "en"
    mixed = detect(fa + " " + en + " " + en)
    assert mixed.lang == "mixed" and 0.2 < mixed.scores["arabic_script"] < 0.8
    assert detect("").lang == "other" and detect("۱۲۳ ۴۵").lang == "other"
    r = detect(fa)
    assert r.scores["fa_vs_ar"] > 0.5 and r.method in ("heuristic", "lingua")
