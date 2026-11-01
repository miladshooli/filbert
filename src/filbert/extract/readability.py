"""گام ۱ — بازنویسی الگوریتم Readability (Mozilla) روی selectolax.

امتیازدهی: برای هر پاراگراف (`p/td/pre/blockquote` و `div` بدون فرزند بلوکی) با متن ≥ ۲۵ کاراکتر:
`1 + تعداد ویرگول (، و ,) + min(3, len//100)`؛ امتیاز به والد (کامل) و پدربزرگ (نصف) منتشر می‌شود.
امتیاز اولیه هر کاندید = امتیاز تگ + وزن class/id (از YAML). امتیاز نهایی × `(1 − link_density)`.
بهترین کاندید انتخاب و خواهر/برادرهای با امتیاز ≥ max(10, 20٪ بهترین) الحاق می‌شوند.
خروجی: `list[Block]` به ترتیب سند با XPath.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from filbert.extract.blocks import (
    OUTPUT_BLOCK_TAGS,
    RawBlock,
    collect_blocks,
    emit_block,
    ensure_h1,
    join_text,
)
from filbert.extract.domtext import (
    Node,
    Tree,
    class_id,
    has_block_child,
    inner_text_len,
    link_density,
    xpath_of,
)
from filbert.extract.rules import ReadabilityRules

log = logging.getLogger(__name__)

SOURCE = "readability"
PARAGRAPH_TAGS: frozenset[str] = frozenset({"p", "td", "pre", "blockquote"})
CONTAINER_TAGS: frozenset[str] = frozenset(
    {
        "div",
        "section",
        "article",
        "main",
        "body",
        "header",
        "li",
        "dd",
        "dt",
        "dl",
        "span",
        "font",
        "center",
        "details",
        "summary",
        "hgroup",
        "fieldset",
        "address",
    }
)
_COMMAS = ("،", ",")


@dataclass(slots=True)
class Candidate:
    node: Node
    score: float
    text_len: int = 0


@dataclass(slots=True)
class ReadabilityResult:
    blocks: list[RawBlock] = field(default_factory=list)
    top_xpath: str | None = None
    top_score: float = 0.0
    text_len: int = 0
    candidates: int = 0

    @property
    def text(self) -> str:
        return join_text(self.blocks)


def class_weight(node: Node, rules: ReadabilityRules) -> float:
    cid = class_id(node)
    if not cid:
        return 0.0
    w = 0.0
    if rules.negative.search(cid):
        w -= rules.class_weight
    if rules.positive.search(cid):
        w += rules.class_weight
    return w


def _base_score(node: Node, rules: ReadabilityRules) -> float:
    return rules.tag_scores.get(node.tag, 0.0) + class_weight(node, rules)


def _is_paragraph(node: Node) -> bool:
    tag = node.tag
    if tag in PARAGRAPH_TAGS:
        return True
    return tag == "div" and not has_block_child(node)


def score_candidates(body: Node, rules: ReadabilityRules) -> dict[int, Candidate]:
    """یک پیمایش روی body؛ کاندیدها را با کلید `mem_id` برمی‌گرداند."""
    cands: dict[int, Candidate] = {}
    min_chars = rules.min_paragraph_chars

    def get(n: Node) -> Candidate:
        c = cands.get(n.mem_id)
        if c is None:
            c = Candidate(node=n, score=_base_score(n, rules))
            cands[n.mem_id] = c
        return c

    for n in body.traverse():
        if not n.is_element_node or not _is_paragraph(n):
            continue
        text = n.text(deep=True).strip()
        n_chars = len(text)
        if n_chars < min_chars:
            continue
        parent = n.parent
        if parent is None or parent.tag in ("html", "-undef") or parent.is_document_node:
            continue
        score = 1.0 + sum(text.count(c) for c in _COMMAS) + min(3, n_chars // 100)
        get(parent).score += score
        grand = parent.parent
        if grand is not None and grand.is_element_node and grand.tag != "html":
            get(grand).score += score / 2

    for c in cands.values():
        c.score *= 1.0 - link_density(c.node)
        c.text_len = inner_text_len(c.node)
    return cands


def _element_children(node: Node) -> list[Node]:
    out: list[Node] = []
    c = node.child
    while c is not None:
        if c.is_element_node:
            out.append(c)
        c = c.next
    return out


def _subtree_best(cands: dict[int, Candidate]) -> dict[int, float]:
    """بهترین امتیاز کاندید در زیردرخت هر عنصر (برای مقایسه خواهر/برادرهای ظرف)."""
    best: dict[int, float] = {}
    for c in cands.values():
        cur: Node | None = c.node
        while cur is not None and cur.tag != "html" and not cur.is_document_node:
            mid = cur.mem_id
            if best.get(mid, float("-inf")) >= c.score:
                break  # اجداد بالاتر قبلاً مقدار ≥ گرفته‌اند
            best[mid] = c.score
            cur = cur.parent
    return best


def _multi_part_level(
    top: Candidate, cands: dict[int, Candidate], rules: ReadabilityRules, max_up: int = 3
) -> list[Node] | None:
    """برای صفحات چندبخشی (انجمن، لندینگ): در یکی از ۳ سطح بالاتر، اگر کنار ظرفِ بهترین
    کاندید دست‌کم دو خواهر/برادر دیگر (یا یکی با همان class) با امتیاز زیردرخت ≥ ۲۰٪ بهترین
    باشد، همان سطح، سطح محتوا است و فرزندان واجد شرط (به ترتیب سند) برگردانده می‌شوند."""
    thr = max(1.0, top.score * rules.sibling_threshold_ratio)
    best = _subtree_best(cands)
    anc = top.node.parent
    containing = top.node
    for _ in range(max_up):
        if anc is None or anc.tag in ("html", "-undef") or anc.is_document_node:
            return None
        children = _element_children(anc)
        good_ids = {
            ch.mem_id
            for ch in children
            if ch.mem_id != containing.mem_id and best.get(ch.mem_id, 0.0) >= thr
        }
        cid = class_id(containing)
        same_class = bool(cid) and any(
            class_id(ch) == cid for ch in children if ch.mem_id in good_ids
        )
        if len(good_ids) >= 2 or (good_ids and same_class):
            good_classes = {class_id(ch) for ch in children if ch.mem_id in good_ids}
            good_classes.add(cid)
            good_classes.discard("")
            return [
                ch
                for ch in children
                if ch.mem_id == containing.mem_id
                or ch.mem_id in good_ids
                or (class_id(ch) in good_classes and best.get(ch.mem_id, 0.0) > 0)
            ]
        containing = anc
        anc = anc.parent
    return None


def _select_content_nodes(
    top: Candidate, cands: dict[int, Candidate], rules: ReadabilityRules
) -> list[Node]:
    threshold = max(rules.sibling_threshold_min, top.score * rules.sibling_threshold_ratio)
    parent = top.node.parent
    if parent is None:
        return [top.node]
    multi = _multi_part_level(top, cands, rules)
    if multi is not None:
        return multi
    chosen: list[Node] = []
    sib = parent.child
    while sib is not None:
        if sib.is_element_node:
            if sib.mem_id == top.node.mem_id:
                chosen.append(sib)
            else:
                c = cands.get(sib.mem_id)
                bonus = 0.0
                if c is not None and class_id(sib) == class_id(top.node) and class_id(sib):
                    bonus = top.score * 0.2
                if c is not None and c.score + bonus >= threshold:
                    chosen.append(sib)
                elif sib.tag == "p" or (sib.tag == "div" and not has_block_child(sib)):
                    ld = link_density(sib)
                    txt = sib.text(deep=True).strip()
                    if (len(txt) > 80 and ld < 0.25) or (
                        len(txt) <= 80 and ld == 0 and txt.endswith((".", "۔", "!", "؟", "?"))
                    ):
                        chosen.append(sib)
        sib = sib.next
    return chosen or [top.node]


def extract(tree: Tree, rules: ReadabilityRules, base_url: str | None = None) -> ReadabilityResult:
    """درخت (پس از preclean) → بلوک‌های محتوای اصلی."""
    body = tree.body
    if body is None:
        return ReadabilityResult()
    cands = score_candidates(body, rules)
    res = ReadabilityResult(candidates=len(cands))
    if not cands:
        # صفحه بدون پاراگراف قابل امتیاز → همه body
        collect_blocks(body, base_url, res.blocks, source=SOURCE)
        res.top_xpath = xpath_of(body)
        res.text_len = len(res.text)
        return res

    top = max(cands.values(), key=lambda c: c.score)
    if top.node.tag == "body" or top.score <= 0:
        nodes = [top.node]
    else:
        nodes = _select_content_nodes(top, cands, rules)
    for n in nodes:
        if n.tag in OUTPUT_BLOCK_TAGS:
            emit_block(n, n.tag, base_url, res.blocks, source=SOURCE)
        else:
            collect_blocks(n, base_url, res.blocks, source=SOURCE)
    ensure_h1(body, res.blocks, base_url, source=SOURCE)
    res.top_xpath = xpath_of(top.node)
    res.top_score = round(top.score, 2)
    res.text_len = len(res.text)
    log.debug("readability top=%s score=%.1f blocks=%d", res.top_xpath, top.score, len(res.blocks))
    return res
