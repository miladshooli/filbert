import pytest

from filbert.extract.domtext import parse
from filbert.extract.preclean import preclean
from filbert.extract.rules import load_rules

RULES = load_rules().preclean


def clean(html: str) -> str:
    t = parse(html)
    preclean(t, RULES)
    return t.body.html


@pytest.mark.parametrize(
    "tag",
    [
        "script",
        "style",
        "noscript",
        "template",
        "iframe",
        "svg",
        "canvas",
        "form",
        "nav",
        "aside",
        "footer",
    ],
)
def test_remove_tags(tag: str) -> None:
    out = clean(f"<body><{tag}>بد</{tag}><p>خوب</p></body>")
    assert f"<{tag}" not in out
    assert "خوب" in out


def test_inputs_and_buttons_removed() -> None:
    out = clean(
        "<body><input value='x'><select><option>a</option></select><button>بزن</button><p>خوب</p></body>"
    )
    assert "<input" not in out and "<select" not in out and "بزن" not in out and "خوب" in out


@pytest.mark.parametrize(
    "attrs",
    [
        "hidden",
        'aria-hidden="true"',
        'style="display:none"',
        'style="display: none ;"',
        'style="visibility:hidden"',
    ],
)
def test_hidden_removed(attrs: str) -> None:
    out = clean(f"<body><div {attrs}>مخفی</div><p>آشکار</p></body>")
    assert "مخفی" not in out and "آشکار" in out


def test_large_hidden_streaming_container_kept() -> None:
    body = (
        '<body><nav>منو</nav><div hidden id="S:0"><h1>تیتر</h1><p>'
        + "متن اصلی مقاله. " * 40
        + "</p></div><div hidden>کوچک</div></body>"
    )
    out = clean(body)
    assert "متن اصلی مقاله" in out and "کوچک" not in out
    assert "hidden" not in out.split("<h1>")[0]  # صفت hidden برداشته شده


def test_aria_hidden_false_kept() -> None:
    assert "متن" in clean('<body><div aria-hidden="false">متن</div></body>')


def test_comments_removed() -> None:
    out = clean("<body><!-- کامنت --><p>متن</p></body>")
    assert "کامنت" not in out and "متن" in out


@pytest.mark.parametrize(
    "cid",
    [
        'class="comments"',
        'id="share-buttons"',
        'class="social-links"',
        'class="related-posts"',
        'id="sidebar"',
        'class="breadcrumb"',
        'class="cookie-notice"',
        'class="popup"',
        'class="modal fade"',
        'id="newsletter"',
        'class="promo-box"',
        'class="advert"',
        'class="banner"',
        'id="main-menu"',
        'class="pagination"',
        # فینگلیش
        'class="nazarat"',
        'id="didgah-ha"',
        'class="eshterak-khabarname"',
        'class="tabligh"',
        'class="matalebe-mortabet"',
        'class="agahi"',
        'class="Peyvand-ha"',
    ],
)
def test_negative_patterns_removed(cid: str) -> None:
    out = clean(f"<body><div {cid}>زائد</div><p>متن</p></body>")
    assert "زائد" not in out, cid
    assert "متن" in out


@pytest.mark.parametrize(
    "cid",
    [
        'class="post-content"',
        'id="main"',
        'class="entry-body"',
        'class="matn-khabar"',
        'class="article-text"',
    ],
)
def test_content_classes_kept(cid: str) -> None:
    assert "متن" in clean(f"<body><div {cid}><p>متن</p></div></body>")


def test_maybe_candidate_protects_from_negative() -> None:
    # share در class هست اما content هم هست → حذف نشود
    assert "متن" in clean('<body><div class="share-content-wrapper"><p>متن</p></div></body>')


def test_header_h1_inside_article_kept() -> None:
    html = """<body>
      <header class="site-header menu">سایت</header>
      <article><header class="post-header menu"><h1 id="menu-title">تیتر مقاله</h1></header><p>بدنه</p></article>
    </body>"""
    out = clean(html)
    assert "تیتر مقاله" in out
    assert "سایت" not in out  # هدر سایت با الگوی menu حذف می‌شود


def test_container_of_article_not_removed() -> None:
    out = clean('<body><div class="sidebar-layout"><article><p>متن اصلی</p></article></div></body>')
    assert "متن اصلی" in out


def test_tables_pre_blockquote_kept() -> None:
    html = "<body><table><tr><td>کارمزد</td></tr></table><pre>code</pre><blockquote>نقل</blockquote><figure><figcaption>ش</figcaption></figure></body>"
    out = clean(html)
    for s in ("کارمزد", "code", "نقل", "<figure>"):
        assert s in out


def test_ui_phrases_removed_but_real_text_kept() -> None:
    html = "<body><article><p>متن اصلی مقاله که باید بماند.</p><p>کپی لینک</p><a href='/s'>اشتراک‌گذاری</a><span>نمایش بیشتر</span><p>گزارش سالانه شرکت منتشر شد.</p></article></body>"
    out = clean(html)
    assert "متن اصلی" in out and "گزارش سالانه" in out
    assert "کپی لینک" not in out and "اشتراک" not in out and "نمایش بیشتر" not in out


def test_stats() -> None:
    t = parse(
        "<body><script></script><div hidden>x</div><div class='comments'>c</div><!--k--><p>م</p></body>"
    )
    st = preclean(t, RULES)
    assert (st.removed_tags, st.removed_hidden, st.removed_patterns, st.removed_comments) == (
        1,
        1,
        1,
        1,
    )
