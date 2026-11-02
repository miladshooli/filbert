from filbert.extract.blocks import RawBlock, collect_blocks
from filbert.extract.domtext import parse
from filbert.extract.markdown import block_to_markdown
from filbert.pipeline import extract_html
from tests.conftest import fixture_html


def md_of(html: str, base: str | None = None) -> list[str]:
    tree = parse(html)
    blocks: list[RawBlock] = []
    collect_blocks(tree.body, base, blocks, source="t")
    return [block_to_markdown(b.node, b.type, base) for b in blocks]


def test_headings_paragraph_inline() -> None:
    out = md_of(
        '<body><h2>تیتر <em>کج</em></h2><p>متن <strong>مهم</strong> و <a href="/l">لینک</a> و <code>x_y</code> و snake_case</p></body>',
        "https://a.ir/",
    )
    assert out == ["## تیتر *کج*", "متن **مهم** و [لینک](https://a.ir/l) و `x_y` و snake\\_case"]


def test_lists_nested_and_ordered() -> None:
    out = md_of(
        "<body><ul><li>یک</li><li>دو<ul><li>دو-الف</li></ul></li></ul><ol><li>اول</li><li>دوم</li></ol></body>"
    )
    assert out == ["- یک\n- دو\n  - دو-الف", "1. اول\n2. دوم"]


def test_table_pipe_and_raw() -> None:
    simple = md_of(
        "<body><table><thead><tr><th>مدل</th><th>قیمت</th></tr></thead><tbody><tr><td>الف</td><td>۴٬۵۰۰</td></tr></tbody></table></body>"
    )
    assert simple == ["| مدل | قیمت |\n| --- | --- |\n| الف | ۴٬۵۰۰ |"]
    raw = md_of("<body><table><tr><td>چند<br>خط</td><td>۹</td></tr></table></body>")
    assert raw[0].startswith('<table dir="auto">') and "چند<br>خط" in raw[0]
    noheader = md_of(
        "<body><table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table></body>"
    )
    assert noheader == ["| a | b |\n| --- | --- |\n| c | d |"]


def test_pre_blockquote_figure() -> None:
    out = md_of(
        '<body><pre><code>seed: 24 words\nline2</code></pre><blockquote><p>نقل</p><p>دوم</p></blockquote><figure><img data-src="/i.png" alt="ت"><figcaption>شرح</figcaption></figure></body>',
        "https://a.ir/",
    )
    assert out == [
        "```\nseed: 24 words\nline2\n```",
        "> نقل\n>\n> دوم",
        "![ت](https://a.ir/i.png)\n\nشرح",
    ]


def test_zwnj_and_pipeline_markdown() -> None:
    rec = extract_html(fixture_html("blog.html"), "https://blog.example.ir/x/")
    md = rec.content.markdown
    assert md.startswith("# چطور کیف پول سخت‌افزاری بخریم؟")
    assert "\u200c" in md and "| مدل | قیمت تقریبی | صفحه نمایش |" in md
    assert "1. پشتیبانی از کوین‌هایی" in md and "```\nseed phrase" in md
    assert "> امنیت واقعی" in md
