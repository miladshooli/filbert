"""بلوک مشترک سه استخراج‌گر: `RawBlock` (با ارجاع به نود) و منطق مشترک تولید بلوک از زیردرخت.

کلید رأی‌گیری هر بلوک = XPath نرمال‌شده + hash متن؛ ترتیب خروجی = ترتیب سند (`doc_order`).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from filbert.extract.cleanhtml import sanitize_node
from filbert.extract.domtext import (
    Node,
    has_block_child,
    inner_text_len,
    link_density,
    node_text,
    xpath_of,
)
from filbert.extract.stats import NodeStats, compute_stats
from filbert.models import Block

OUTPUT_BLOCK_TAGS: frozenset[str] = frozenset(
    {"h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "table", "blockquote", "pre", "figure"}
)
HEADING_TAGS: frozenset[str] = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SKIP_TAGS: frozenset[str] = frozenset({"br", "hr", "a"})
# shortcode وردپرسیِ رندرنشده که به‌تنهایی یک بلوک شده: [tie_list type="x"] ، [/tie_list] ، [caption id=..]
_SHORTCODE_RE = re.compile(r"^\s*\[/?[A-Za-z_][\w-]*(?:\s[^\]]*)?\]\s*$")
Predicate = Callable[[Node], bool]


@dataclass(slots=True)
class PageContext:
    """کش‌های یک صفحه که بین سه استخراج‌گر مشترک است: آمار نود، متن/HTML/XPath هر بلوک."""

    stats: dict[int, NodeStats] | None = None
    _candidates: list[tuple[Node, str]] | None = None
    _text: dict[int, str] = field(default_factory=dict)
    _html: dict[tuple[int, str], str] = field(default_factory=dict)
    _xpath: dict[int, str] = field(default_factory=dict)

    @classmethod
    def build(cls, body: Node | None) -> PageContext:
        return cls(stats=compute_stats(body) if body is not None else None)

    def candidates(self, body: Node) -> list[tuple[Node, str]]:
        """فهرست بلوک‌های کاندید صفحه (یک پیمایش؛ مشترک بین استخراج‌گرها)."""
        if self._candidates is None:
            self._candidates = iter_candidate_blocks(body)
        return self._candidates

    def node_text(self, node: Node) -> str:
        mid = node.mem_id
        t = self._text.get(mid)
        if t is None:
            t = self._text[mid] = node_text(node)
        return t

    def html(self, node: Node, tag: str, base_url: str | None) -> str:
        key = (node.mem_id, tag)
        h = self._html.get(key)
        if h is None:
            h = self._html[key] = sanitize_node(node, base_url, as_tag=tag)
        return h

    def xpath(self, node: Node) -> str:
        mid = node.mem_id
        x = self._xpath.get(mid)
        if x is None:
            x = self._xpath[mid] = xpath_of(node)
        return x

    def text_len(self, node: Node) -> int:
        if self.stats is not None:
            s = self.stats.get(node.mem_id)
            return s.chars if s is not None else 0
        return inner_text_len(node)

    def link_density(self, node: Node) -> float:
        if self.stats is not None:
            s = self.stats.get(node.mem_id)
            if s is None or s.chars == 0:
                return 0.0
            return min(1.0, s.link_chars / s.chars)
        return link_density(node)


def text_hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=6).hexdigest()


@dataclass(slots=True)
class RawBlock:
    node: Node
    type: str
    text: str
    html: str
    xpath: str
    source: str = ""

    @property
    def key(self) -> str:
        return f"{self.xpath}#{text_hash(self.text)}"

    def to_block(self, votes: int = 1) -> Block:
        return Block(type=self.type, text=self.text, html=self.html, xpath=self.xpath, votes=votes)  # type: ignore[arg-type]


def doc_order(body: Node) -> dict[int, int]:
    """`mem_id` → اندیس پیش‌ترتیب (برای مرتب‌سازی بلوک‌ها به ترتیب سند)."""
    return {n.mem_id: i for i, n in enumerate(body.traverse())}


def emit_block(
    node: Node,
    tag: str,
    base_url: str | None,
    out: list[RawBlock],
    *,
    source: str,
    min_chars: int = 0,
    predicate: Predicate | None = None,
    ctx: PageContext | None = None,
) -> None:
    """یک عنصر را (اگر شرایط کیفیت را داشت) به بلوک تبدیل می‌کند."""
    if predicate is not None and not predicate(node):
        return
    ld = ctx.link_density if ctx is not None else link_density
    text = ctx.node_text(node) if ctx is not None else node_text(node)
    if text and _SHORTCODE_RE.match(text):
        return
    has_img = node.tag == "img" or node.css_first("img") is not None
    if tag in ("ul", "ol", "table"):
        if ld(node) > 0.5:
            return  # فهرست ناوبری / جدول لینک
    elif tag == "figure":
        if not has_img and not text:
            return
    elif tag == "pre" or tag in HEADING_TAGS:
        if not text:
            return
    else:
        if not text and not has_img:
            return
        if not text and has_img:
            tag = "figure"  # پاراگرافی که فقط تصویر دارد (<p><img>) → figure
        elif len(text) < max(min_chars, 100) and ld(node) > 0.5:
            return  # تکه لینکی کوتاه (ناوبری، اشتراک‌گذاری)
    if ctx is not None:
        html, xpath = ctx.html(node, tag, base_url), ctx.xpath(node)
    else:
        html, xpath = sanitize_node(node, base_url, as_tag=tag), xpath_of(node)
    out.append(RawBlock(node=node, type=tag, text=text, html=html, xpath=xpath, source=source))


def collect_blocks(
    node: Node,
    base_url: str | None,
    out: list[RawBlock],
    *,
    source: str,
    min_chars: int = 0,
    predicate: Predicate | None = None,
    ctx: PageContext | None = None,
) -> None:
    """بلوک‌های خروجی زیردرخت یک نود به ترتیب سند. ظرف‌ها (div/section/…) باز می‌شوند؛
    ظرف بدون فرزند بلوکی مثل `p` رفتار می‌کند؛ `img` تنها → `figure`."""
    for child in node.iter():
        if not child.is_element_node:
            continue
        tag = child.tag
        if tag in OUTPUT_BLOCK_TAGS:
            emit_block(
                child,
                tag,
                base_url,
                out,
                source=source,
                min_chars=min_chars,
                predicate=predicate,
                ctx=ctx,
            )
        elif tag == "img":
            emit_block(child, "figure", base_url, out, source=source, predicate=predicate, ctx=ctx)
        elif tag in _SKIP_TAGS:
            continue
        elif has_block_child(child):
            collect_blocks(
                child,
                base_url,
                out,
                source=source,
                min_chars=min_chars,
                predicate=predicate,
                ctx=ctx,
            )
        else:
            emit_block(
                child,
                "p",
                base_url,
                out,
                source=source,
                min_chars=min_chars,
                predicate=predicate,
                ctx=ctx,
            )


def collect_from_candidates(
    ctx: PageContext,
    body: Node,
    base_url: str | None,
    out: list[RawBlock],
    *,
    source: str,
    predicate: Predicate,
    min_chars: int = 0,
) -> None:
    """معادل `collect_blocks(body, …, predicate)` اما روی فهرست کاندید کش‌شده (بدون پیمایش دوباره درخت)."""
    for node, tag in ctx.candidates(body):
        emit_block(
            node,
            tag,
            base_url,
            out,
            source=source,
            min_chars=min_chars,
            predicate=predicate,
            ctx=ctx,
        )


def iter_candidate_blocks(node: Node) -> list[tuple[Node, str]]:
    """همان پیمایش `collect_blocks` اما بدون فیلتر کیفیت: (نود، نوع بلوک) برای امتیازدهی ویژگی‌ها."""
    out: list[tuple[Node, str]] = []

    def walk(n: Node) -> None:
        for child in n.iter():
            if not child.is_element_node:
                continue
            tag = child.tag
            if tag in OUTPUT_BLOCK_TAGS:
                out.append((child, tag))
            elif tag == "img":
                out.append((child, "figure"))
            elif tag in _SKIP_TAGS:
                continue
            elif has_block_child(child):
                walk(child)
            else:
                out.append((child, "p"))

    walk(node)
    return out


def ensure_h1(
    body: Node,
    blocks: list[RawBlock],
    base_url: str | None,
    *,
    source: str,
    ctx: PageContext | None = None,
) -> None:
    """تیتر صفحه (اولین h1 باقی‌مانده پس از preclean) اگر در خروجی نیست، به ابتدا اضافه می‌شود."""
    if any(b.type == "h1" for b in blocks):
        return
    h1 = body.css_first("h1")
    if h1 is None:
        return
    text = ctx.node_text(h1) if ctx is not None else node_text(h1)
    if not text:
        return
    html = ctx.html(h1, "h1", base_url) if ctx is not None else sanitize_node(h1, base_url)
    xpath = ctx.xpath(h1) if ctx is not None else xpath_of(h1)
    blocks.insert(0, RawBlock(node=h1, type="h1", text=text, html=html, xpath=xpath, source=source))


def join_text(blocks: list[RawBlock]) -> str:
    return "\n\n".join(b.text for b in blocks if b.text)
