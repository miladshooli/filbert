import json

import pytest

from filbert.extract.cleanhtml import ALLOWED_TAGS, build_article, sanitize_node
from filbert.extract.domtext import parse, xpath_of
from filbert.extract.preclean import preclean
from filbert.extract.readability import extract
from filbert.extract.rules import load_rules
from tests.conftest import FIXTURES, fixture_html

RULES = load_rules()
FIXTURE_NAMES = ["news", "blog", "product", "landing", "forum"]


def run(name: str):
    tree = parse(fixture_html(f"{name}.html"))
    preclean(tree, RULES.preclean)
    return extract(tree, RULES.readability, base_url="https://example.ir/x/")


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_fixture_expectations(name: str) -> None:
    exp = json.loads((FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8"))
    res = run(name)
    text = res.text
    missing = [s for s in exp["include"] if s not in text]
    leaked = [s for s in exp["exclude"] if s in text]
    assert not missing, f"{name}: missing {missing}\n---\n{text}"
    assert not leaked, f"{name}: leaked {leaked}\n---\n{text}"
    assert len(res.blocks) >= exp["min_blocks"], [b.type for b in res.blocks]
    types = {b.type for b in res.blocks}
    assert set(exp["types"]) <= types, types


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_blocks_are_clean_and_ordered(name: str) -> None:
    res = run(name)
    for b in res.blocks:
        assert b.xpath.startswith("/html/body/")
        assert b.html.startswith(f"<{b.type}")
        assert "class=" not in b.html and "style=" not in b.html and "<div" not in b.html
        assert "<span" not in b.html and "<script" not in b.html
    # ترتیب سند: XPath بلوک‌ها به ترتیب ظاهر باید باشد؛ تست با متن سند
    html = fixture_html(f"{name}.html")
    pos = 0
    for b in res.blocks:
        snippet = (
            b.text.split()[0][:8] if b.text.split() else ""
        )  # یک کلمه؛ متن بین تگ‌های inline شکسته می‌شود
        if not snippet:
            continue
        i = html.find(snippet, pos)
        assert i >= 0, f"{name}: block out of order or missing: {snippet!r}"
        pos = i


def test_zwnj_preserved_in_blocks() -> None:
    res = run("blog")
    assert "می‌خواهیم" in res.text  # با ZWNJ
    assert "‌" in res.text


def test_image_urls_absolute_and_alt_kept() -> None:
    res = run("news")
    fig = next(b for b in res.blocks if b.type == "figure")
    assert 'src="https://example.ir/uploads/btc-chart.png"' in fig.html
    assert 'alt="نمودار قیمت بیت‌کوین"' in fig.html


def test_xpath() -> None:
    t = parse("<html><body><div><p>a</p><p>b</p></div><div><p>c</p></div></body></html>")
    ps = t.css("p")
    assert xpath_of(ps[0]) == "/html/body/div[1]/p[1]"
    assert xpath_of(ps[1]) == "/html/body/div[1]/p[2]"
    assert xpath_of(ps[2]) == "/html/body/div[2]/p[1]"


def test_sanitize_node_rules() -> None:
    t = parse(
        '<body><p class="x" style="c" onclick="y">سلام <b>دنیا</b> <span>!</span> <a href="/l" rel="nofollow" target="_blank">لینک</a>'
        ' <a href="javascript:void(0)">بد</a> <img data-src="/i.png" alt="ت" width="3"> <script>x</script></p></body>'
    )
    out = sanitize_node(t.css_first("p"), base_url="https://a.ir/b/")
    assert out == (
        '<p dir="auto">سلام <strong>دنیا</strong> ! <a href="https://a.ir/l">لینک</a> بد '
        '<img src="https://a.ir/i.png" alt="ت"> </p>'
    )
    assert set(ALLOWED_TAGS) >= {"h1", "p", "table", "figure", "a", "strong", "em"}


def test_build_article() -> None:
    art = build_article(['<p dir="auto">الف</p>', '<h2 dir="auto">ب</h2>'])
    assert art.startswith('<article lang="fa" dir="rtl">')
    assert "الف" in art and art.endswith("</article>")


def test_empty_and_minimal_pages() -> None:
    assert extract(parse(""), RULES.readability).blocks == []
    res = extract(parse("<html><body><p>کوتاه</p></body></html>"), RULES.readability)
    assert res.text == "کوتاه"
