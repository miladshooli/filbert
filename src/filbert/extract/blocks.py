"""بلوک مشترک سه استخراج‌گر: `RawBlock` (با ارجاع به نود) و منطق مشترک تولید بلوک از زیردرخت.

کلید رأی‌گیری هر بلوک = XPath نرمال‌شده + hash متن؛ ترتیب خروجی = ترتیب سند (`doc_order`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from filbert.extract.cleanhtml import sanitize_node
from filbert.extract.domtext import Node, has_block_child, link_density, node_text, xpath_of
from filbert.models import Block

OUTPUT_BLOCK_TAGS: frozenset[str] = frozenset(
    {"h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "table", "blockquote", "pre", "figure"}
)
HEADING_TAGS: frozenset[str] = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_SKIP_TAGS: frozenset[str] = frozenset({"br", "hr", "a"})
Predicate = Callable[[Node], bool]


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
) -> None:
    """یک عنصر را (اگر شرایط کیفیت را داشت) به بلوک تبدیل می‌کند."""
    if predicate is not None and not predicate(node):
        return
    text = node_text(node)
    has_img = node.tag == "img" or node.css_first("img") is not None
    if tag in ("ul", "ol", "table"):
        if link_density(node) > 0.5:
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
        if len(text) < max(min_chars, 100) and link_density(node) > 0.5:
            return  # تکه لینکی کوتاه (ناوبری، اشتراک‌گذاری)
    html = sanitize_node(node, base_url, as_tag=tag)
    out.append(
        RawBlock(node=node, type=tag, text=text, html=html, xpath=xpath_of(node), source=source)
    )


def collect_blocks(
    node: Node,
    base_url: str | None,
    out: list[RawBlock],
    *,
    source: str,
    min_chars: int = 0,
    predicate: Predicate | None = None,
) -> None:
    """بلوک‌های خروجی زیردرخت یک نود به ترتیب سند. ظرف‌ها (div/section/…) باز می‌شوند؛
    ظرف بدون فرزند بلوکی مثل `p` رفتار می‌کند؛ `img` تنها → `figure`."""
    for child in node.iter():
        if not child.is_element_node:
            continue
        tag = child.tag
        if tag in OUTPUT_BLOCK_TAGS:
            emit_block(
                child, tag, base_url, out, source=source, min_chars=min_chars, predicate=predicate
            )
        elif tag == "img":
            emit_block(child, "figure", base_url, out, source=source, predicate=predicate)
        elif tag in _SKIP_TAGS:
            continue
        elif has_block_child(child):
            collect_blocks(
                child, base_url, out, source=source, min_chars=min_chars, predicate=predicate
            )
        else:
            emit_block(
                child, "p", base_url, out, source=source, min_chars=min_chars, predicate=predicate
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


def ensure_h1(body: Node, blocks: list[RawBlock], base_url: str | None, *, source: str) -> None:
    """تیتر صفحه (اولین h1 باقی‌مانده پس از preclean) اگر در خروجی نیست، به ابتدا اضافه می‌شود."""
    if any(b.type == "h1" for b in blocks):
        return
    h1 = body.css_first("h1")
    if h1 is None:
        return
    text = node_text(h1)
    if not text:
        return
    blocks.insert(
        0,
        RawBlock(
            node=h1,
            type="h1",
            text=text,
            html=sanitize_node(h1, base_url),
            xpath=xpath_of(h1),
            source=source,
        ),
    )


def join_text(blocks: list[RawBlock]) -> str:
    return "\n\n".join(b.text for b in blocks if b.text)
