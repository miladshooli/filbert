"""ابزارهای مشترک روی درخت selectolax (lexbor): متن، چگالی لینک، XPath."""

from __future__ import annotations

import re

from selectolax.lexbor import LexborHTMLParser, LexborNode

Node = LexborNode
Tree = LexborHTMLParser

BLOCK_TAGS: frozenset[str] = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "dd",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
        "body",
        "br",
        "caption",
        "summary",
    }
)
_WS_RE = re.compile(r"[ \t\r\f\v ]+")
_NL_RE = re.compile(r"\n\s*\n+")


def class_id(node: Node) -> str:
    a = node.attributes
    return f"{a.get('class') or ''} {a.get('id') or ''}".strip()


def node_text(node: Node) -> str:
    """متن قابل‌مشاهده با مرز خط روی عناصر بلوکی؛ فاصله‌ها فشرده می‌شوند."""
    parts: list[str] = []
    for n in node.traverse(include_text=True):
        tag = n.tag
        if tag == "-text":
            parts.append(n.text_content or "")
        elif tag in BLOCK_TAGS:
            parts.append("\n")
    text = _WS_RE.sub(" ", "".join(parts))
    lines = [ln.strip() for ln in text.split("\n")]
    return _NL_RE.sub("\n\n", "\n".join(lines)).strip()


def inner_text_len(node: Node) -> int:
    return len(node.text(deep=True, strip=False).strip())


def link_density(node: Node) -> float:
    total = inner_text_len(node)
    if total == 0:
        return 0.0
    links = sum(len(a.text(deep=True).strip()) for a in node.css("a"))
    return min(1.0, links / total)


def xpath_of(node: Node) -> str:
    """XPath موقعیتی مثل `/html/body/div[2]/p[1]`."""
    parts: list[str] = []
    cur: Node | None = node
    while cur is not None and cur.tag not in ("-undef", "html") and not cur.is_document_node:
        tag = cur.tag
        idx = 1
        sib = cur.prev
        while sib is not None:
            if sib.tag == tag:
                idx += 1
            sib = sib.prev
        parts.append(f"{tag}[{idx}]")
        cur = cur.parent
    parts.append("html")
    return "/" + "/".join(reversed(parts))


def has_ancestor(node: Node, tags: frozenset[str]) -> bool:
    cur = node.parent
    while cur is not None and cur.tag != "html":
        if cur.tag in tags:
            return True
        cur = cur.parent
    return False


def has_block_child(node: Node) -> bool:
    child = node.child
    while child is not None:
        if child.tag in BLOCK_TAGS:
            return True
        child = child.next
    return False


def parse(html: str) -> Tree:
    """تنها نقطه پارس HTML در filbert."""
    return LexborHTMLParser(html)
