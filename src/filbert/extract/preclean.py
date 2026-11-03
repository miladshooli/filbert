"""گام ۰ — پیش‌پاک‌سازی مشترک درخت قبل از استخراج‌گرها (درخت را درجا تغییر می‌دهد).

۱. حذف تگ‌های غیرمحتوا (`script, style, nav, aside, footer, ...`) و کامنت‌ها.
۲. حذف عناصر مخفی (`hidden`, `aria-hidden="true"`, `display:none`, `visibility:hidden`).
۳. حذف با الگوی class/id (انگلیسی + فینگلیش) — به‌جز `header`/`h1` داخل `article|main`،
   و به‌جز وقتی class/id هم‌زمان الگوی «شاید محتوا» را match کند.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from filbert.extract.domtext import (
    Node,
    Tree,
    class_id,
    has_ancestor,
    has_block_child,
    inner_text_len,
)
from filbert.extract.rules import PrecleanRules

_HIDDEN_STYLE_RE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)
_MAIN_TAGS = frozenset({"article", "main"})
_HEADER_EXCEPTION = frozenset({"header", "h1"})
_UI_LEAF_TAGS = frozenset({"a", "span", "p", "div", "button", "li", "label", "b", "strong"})


@dataclass(slots=True)
class PrecleanStats:
    removed_tags: int = 0
    removed_hidden: int = 0
    removed_patterns: int = 0
    removed_comments: int = 0


def is_hidden(node: Node) -> bool:
    a = node.attributes
    if "hidden" in a:
        return True
    if (a.get("aria-hidden") or "").strip().lower() == "true":
        return True
    style = a.get("style")
    return bool(style and _HIDDEN_STYLE_RE.search(style))


def _unhide(node: Node) -> None:
    for attr in ("hidden", "aria-hidden"):
        if attr in node.attributes:
            del node.attrs[attr]
    style = node.attributes.get("style")
    if style and _HIDDEN_STYLE_RE.search(style):
        del node.attrs["style"]


def matches_negative(node: Node, rules: PrecleanRules) -> bool:
    cid = class_id(node)
    if not cid:
        return False
    return bool(rules.negative.search(cid)) and not rules.maybe_candidate.search(cid)


# عنصر مخفی با ≥۳۰٪ متن body (پس از حذف script) و ≥۵۰۰ کاراکتر، محتواست
# (streaming SSR ری‌اکت: <div hidden id="S:0">) و به‌جای حذف، آشکار می‌شود.
_HIDDEN_KEEP_RATIO = 0.3
_HIDDEN_KEEP_MIN_CHARS = 500


def preclean(tree: Tree, rules: PrecleanRules) -> PrecleanStats:
    """درخت را پاک می‌کند و آمار حذف را برمی‌گرداند. فقط روی `body` کار می‌کند."""
    stats = PrecleanStats()
    body = tree.body
    if body is None:
        return stats
    for tag in rules.remove_tags:
        for n in body.css(tag):
            n.decompose()
            stats.removed_tags += 1
    body_len = max(1, inner_text_len(body))  # پس از حذف script/style

    # یک پیمایش: کامنت، مخفی، الگوها. عناصر در فهرست جمع می‌شوند تا پیمایش هنگام حذف خراب نشود.
    to_remove: list[tuple[Node, str]] = []
    for n in body.traverse(include_text=True):
        if n.is_comment_node:
            to_remove.append((n, "comment"))
            continue
        if not n.is_element_node or n.tag in rules.protected_tags:
            continue
        if rules.ui_phrases and n.tag in _UI_LEAF_TAGS and not has_block_child(n):
            txt = " ".join(n.text(deep=True).replace("\u200c", " ").split()).lower()
            if txt and len(txt) <= 40 and txt in rules.ui_phrases:
                to_remove.append((n, "pattern"))
                continue
        if is_hidden(n):
            if (
                tl := inner_text_len(n)
            ) >= _HIDDEN_KEEP_RATIO * body_len and tl >= _HIDDEN_KEEP_MIN_CHARS:
                _unhide(n)  # ظرف streaming/hydration؛ محتوای واقعی صفحه است
            else:
                to_remove.append((n, "hidden"))
                continue
        if matches_negative(n, rules):
            if n.tag in _HEADER_EXCEPTION and has_ancestor(n, _MAIN_TAGS):
                continue
            if n.css_first("article, main") is not None:
                continue  # ظرفی که محتوای اصلی داخلش است حذف نمی‌شود
            to_remove.append((n, "pattern"))

    seen: set[int] = set()
    for n, kind in to_remove:
        if n.mem_id in seen:
            continue
        seen.add(n.mem_id)
        if n.parent is None:
            continue
        n.decompose()
        if kind == "comment":
            stats.removed_comments += 1
        elif kind == "hidden":
            stats.removed_hidden += 1
        else:
            stats.removed_patterns += 1
    return stats
