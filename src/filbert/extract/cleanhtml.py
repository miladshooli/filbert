"""گام ۵ — ساخت HTML معنایی تمیز مستقیماً از نودهای selectolax (بدون پارس دوم).

فقط تگ‌های مجاز، فقط attribute‌های مجاز (`href`, `src`, `alt`, `colspan`, `rowspan`)،
URLها مطلق می‌شوند، `dir="auto"` روی هر بلوک و `lang`/`dir` روی ریشه `<article>`.
"""

from __future__ import annotations

import html as _html
from collections.abc import Iterable
from urllib.parse import urljoin

from filbert.extract.domtext import Node

ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "ul",
        "ol",
        "li",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "caption",
        "blockquote",
        "pre",
        "code",
        "figure",
        "img",
        "figcaption",
        "a",
        "strong",
        "em",
        "br",
    }
)
# تگ‌هایی که به معادل مجاز نگاشت می‌شوند
TAG_ALIASES: dict[str, str] = {"b": "strong", "i": "em", "dl": "ul", "dd": "li", "dt": "li"}
# تگ‌هایی که با محتوایشان حذف می‌شوند (اگر preclean جا انداخته باشد)
DROP_TAGS: frozenset[str] = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "iframe",
        "svg",
        "canvas",
        "button",
        "input",
        "select",
        "textarea",
        "form",
        "object",
        "embed",
        "head",
        "title",
        "meta",
        "link",
    }
)
VOID_TAGS: frozenset[str] = frozenset({"img", "br"})
ALLOWED_ATTRS: dict[str, tuple[str, ...]] = {
    "a": ("href",),
    "img": ("src", "alt"),
    "td": ("colspan", "rowspan"),
    "th": ("colspan", "rowspan"),
}
_IMG_SRC_FALLBACKS = ("src", "data-src", "data-lazy-src", "data-original")


def img_src(attrs: dict[str, str | None], base_url: str | None) -> str | None:
    for k in _IMG_SRC_FALLBACKS:
        v = (attrs.get(k) or "").strip()
        if v and not v.startswith("data:"):
            return urljoin(base_url, v) if base_url else v
    srcset = attrs.get("srcset") or attrs.get("data-srcset") or ""
    if srcset:
        first = srcset.split(",")[0].strip().split(" ")[0]
        if first:
            return urljoin(base_url, first) if base_url else first
    return None


def _attrs_for(tag: str, node: Node, base_url: str | None) -> str:
    allowed = ALLOWED_ATTRS.get(tag)
    if not allowed:
        return ""
    attrs = node.attributes
    out: list[str] = []
    for name in allowed:
        if tag == "img" and name == "src":
            val = img_src(attrs, base_url)
        else:
            val = attrs.get(name)
            if val is None:
                if tag == "img" and name == "alt":
                    val = ""
                else:
                    continue
            val = val.strip()
            if name == "href":
                if not val or val.lower().startswith(("javascript:", "data:")):
                    continue
                val = urljoin(base_url, val) if base_url else val
        if val is None:
            continue
        out.append(f' {name}="{_html.escape(val, quote=True)}"')
    return "".join(out)


def _serialize(node: Node, base_url: str | None, out: list[str], top: bool) -> None:
    for child in node.iter(include_text=True):
        tag = child.tag
        if tag == "-text":
            out.append(_html.escape(child.text_content or "", quote=False))
            continue
        if not child.is_element_node or tag in DROP_TAGS:
            continue
        tag = TAG_ALIASES.get(tag, tag)
        if tag not in ALLOWED_TAGS:
            _serialize(child, base_url, out, top=False)  # unwrap: فقط فرزندان
            continue
        _emit_element(child, tag, base_url, out, top=False)


def _emit_element(node: Node, tag: str, base_url: str | None, out: list[str], top: bool) -> None:
    attrs = _attrs_for(tag, node, base_url)
    if tag == "img" and 'src="' not in attrs:
        return
    if tag == "a" and 'href="' not in attrs:
        _serialize(node, base_url, out, top=False)  # لینک بی‌مقصد → متن ساده
        return
    dir_attr = ' dir="auto"' if top else ""
    if tag in VOID_TAGS:
        out.append(f"<{tag}{attrs}>")
        return
    out.append(f"<{tag}{dir_attr}{attrs}>")
    _serialize(node, base_url, out, top=False)
    out.append(f"</{tag}>")


def sanitize_node(node: Node, base_url: str | None = None, *, as_tag: str | None = None) -> str:
    """یک بلوک را به HTML تمیز تبدیل می‌کند. `as_tag` نام تگ ریشه را تحمیل می‌کند (مثلاً div→p)."""
    tag = as_tag or TAG_ALIASES.get(node.tag, node.tag)
    out: list[str] = []
    if tag in ALLOWED_TAGS:
        _emit_element(node, tag, base_url, out, top=True)
    else:
        out.append('<p dir="auto">')
        _serialize(node, base_url, out, top=False)
        out.append("</p>")
    return "".join(out)


def build_article(block_htmls: Iterable[str], lang: str = "fa", direction: str = "rtl") -> str:
    body = "\n".join(h for h in block_htmls if h)
    return f'<article lang="{_html.escape(lang)}" dir="{direction}">\n{body}\n</article>'


def build_document(
    article_html: str,
    *,
    title: str | None,
    source_url: str,
    fetched_at: str | None,
    lang: str = "fa",
    direction: str = "rtl",
) -> str:
    """پوسته حداقلی خروجی `.html`: بدون CSS و JS."""
    t = _html.escape(title or source_url)
    footer = (
        f'<footer data-source-url="{_html.escape(source_url, quote=True)}"'
        f' data-fetched-at="{_html.escape(fetched_at or "", quote=True)}">'
        f'<a href="{_html.escape(source_url, quote=True)}">{_html.escape(source_url)}</a></footer>'
    )
    return (
        f'<!doctype html>\n<html lang="{lang}" dir="{direction}">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{t}</title>\n</head>\n<body>\n{article_html}\n{footer}\n</body>\n</html>\n"
    )
