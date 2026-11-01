import pytest

from filbert.fetch.urlnorm import is_internal, normalize_url, registered_domain


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "HTTPS://Nobitex.IR/blog/post/?utm_source=x&utm_medium=y#top",
            "https://nobitex.ir/blog/post/",
        ),
        ("https://nobitex.ir/blog/?b=2&a=1&fbclid=zzz", "https://nobitex.ir/blog/?a=1&b=2"),
        ("https://nobitex.ir/blog/?gclid=1&yclid=2&ref=tw", "https://nobitex.ir/blog/"),
        ("https://nobitex.ir", "https://nobitex.ir/"),
        ("https://nobitex.ir:443/x", "https://nobitex.ir/x"),
        ("http://nobitex.ir:8080/x", "http://nobitex.ir:8080/x"),
        ("https://nobitex.ir/dir/index.html", "https://nobitex.ir/dir/"),
        ("https://nobitex.ir/a?q=سلام", "https://nobitex.ir/a?q=%D8%B3%D9%84%D8%A7%D9%85"),
        ("https://nobitex.ir/a?x=1&x=0", "https://nobitex.ir/a?x=0&x=1"),
        ("https://nobitex.ir/a?empty=", "https://nobitex.ir/a?empty="),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_idempotent() -> None:
    u = normalize_url("https://Nobitex.ir/blog/?utm_x=1&z=2&a=1#frag")
    assert normalize_url(u) == u


def test_relative_with_base() -> None:
    assert (
        normalize_url("../x?a=1", base="https://nobitex.ir/blog/post/")
        == "https://nobitex.ir/blog/x?a=1"
    )
    assert (
        normalize_url("//cdn.nobitex.ir/i.png", base="https://nobitex.ir/")
        == "https://cdn.nobitex.ir/i.png"
    )


def test_registered_domain() -> None:
    assert registered_domain("https://blog.nobitex.ir/x") == "nobitex.ir"
    assert registered_domain("fa.wikipedia.org") == "wikipedia.org"
    assert registered_domain("https://foo.co.uk/") == "foo.co.uk"
    assert registered_domain("https://a.github.io/") == "a.github.io"


def test_is_internal() -> None:
    page = "https://nobitex.ir/blog/post/"
    assert is_internal("https://nobitex.ir/markets", page)
    assert is_internal("https://blog.nobitex.ir/x", page)
    assert is_internal("/relative", page)
    assert not is_internal("https://zoomit.ir/", page)
    assert not is_internal("https://nobitex.ir.evil.com/", page)
