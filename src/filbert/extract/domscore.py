"""گام ۳ — امتیاز ویژگی‌های DOM (الگوی learnhtml) با وزن‌های ثابت؛ فاز ۵: lightgbm روی همین ویژگی‌ها.

برای هر بلوک کاندید (همان پیمایش `collect_blocks`): طول متن، نسبت کاراکتر لینک، علائم جمله،
عمق، خواهر/برادرهای هم‌تگ، میانگین طول کلمه، وجود عدد، فاصله از بزرگ‌ترین بلوک، امتیاز class/id اجداد.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from filbert.extract.blocks import (
    HEADING_TAGS,
    RawBlock,
    emit_block,
    ensure_h1,
    iter_candidate_blocks,
    join_text,
)
from filbert.extract.domtext import Node, Tree, class_id, link_density, node_text, xpath_of
from filbert.extract.rules import ReadabilityRules

SOURCE = "dom"
_SENTENCE_PUNCT_RE = re.compile(r"[.،؛!؟?]")
_DIGIT_RE = re.compile(r"[\d۰-۹]")

DEFAULT_WEIGHTS: dict[str, float] = {
    "bias": -1.6,
    "length": 2.8,  # min(1, len/300)
    "link_ratio": -3.2,
    "punct": 0.5,  # min(3, count)
    "class_pos": 1.2,
    "class_neg": -1.8,
    "dist_largest": -1.8,  # 0..1 در ترتیب سند
    "heading_near": 1.4,  # هدینگ در فاصله < 0.25 از بزرگ‌ترین بلوک
    "siblings": 0.4,  # min(1, same-tag siblings / 3)
    "depth": -0.12,  # max(0, depth - 8)
    "avg_word": -0.3,  # میانگین طول کلمه > 12 (کد/URL)
    "has_number": 0.2,
    "list_or_table": 0.6,
    "quote_or_code": 0.8,  # blockquote/pre داخل محتوا معمولاً خودِ محتواست
    "neighbor": 0.7,  # میانگین امتیاز مثبت دو همسایه در ترتیب سند (هموارسازی)
}


@dataclass(slots=True)
class Features:
    length: float
    link_ratio: float
    punct: float
    class_pos: float
    class_neg: float
    dist_largest: float
    heading_near: float
    siblings: float
    depth: float
    avg_word: float
    has_number: float
    list_or_table: float
    quote_or_code: float
    neighbor: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {k: getattr(self, k) for k in self.__slots__}


@dataclass(slots=True)
class DomResult:
    blocks: list[RawBlock] = field(default_factory=list)
    scored: int = 0
    largest_xpath: str | None = None

    @property
    def text(self) -> str:
        return join_text(self.blocks)


def _ancestor_class_score(
    node: Node, rules: ReadabilityRules, levels: int = 3
) -> tuple[float, float]:
    pos = neg = 0.0
    cur: Node | None = node
    for i in range(levels + 1):
        if cur is None or cur.tag in ("body", "html"):
            break
        cid = class_id(cur)
        if cid:
            w = 1.0 / (i + 1)
            if rules.positive.search(cid):
                pos = max(pos, w)
            if rules.negative.search(cid):
                neg = max(neg, w)
        cur = cur.parent
    return pos, neg


def _depth(node: Node) -> int:
    d = 0
    cur = node.parent
    while cur is not None and cur.tag != "html":
        d += 1
        cur = cur.parent
    return d


def _same_tag_siblings(node: Node) -> int:
    n = 0
    sib = node.parent.child if node.parent is not None else None
    while sib is not None:
        if sib.tag == node.tag and sib.mem_id != node.mem_id:
            n += 1
        sib = sib.next
    return n


def compute_features(
    cands: list[tuple[Node, str]], texts: list[str], rules: ReadabilityRules
) -> list[Features]:
    if not cands:
        return []
    lengths = [len(t) for t in texts]
    largest = max(range(len(cands)), key=lambda i: lengths[i])
    span = max(1, len(cands) - 1)
    feats: list[Features] = []
    for i, ((node, tag), text) in enumerate(zip(cands, texts, strict=True)):
        words = text.split()
        avg_word = (sum(len(w) for w in words) / len(words)) if words else 0.0
        pos, neg = _ancestor_class_score(node, rules)
        dist = abs(i - largest) / span
        feats.append(
            Features(
                length=min(1.0, len(text) / 300),
                link_ratio=link_density(node),
                punct=float(min(3, len(_SENTENCE_PUNCT_RE.findall(text)))),
                class_pos=pos,
                class_neg=neg,
                dist_largest=dist,
                heading_near=1.0 if (tag in HEADING_TAGS and dist < 0.25) else 0.0,
                siblings=min(1.0, _same_tag_siblings(node) / 3),
                depth=float(max(0, _depth(node) - 8)),
                avg_word=1.0 if avg_word > 12 else 0.0,
                has_number=1.0 if _DIGIT_RE.search(text) else 0.0,
                list_or_table=1.0 if tag in ("ul", "ol", "table") else 0.0,
                quote_or_code=1.0 if tag in ("blockquote", "pre") else 0.0,
            )
        )
    return feats


def linear_score(f: Features, w: dict[str, float]) -> float:
    s = w["bias"]
    for k, v in f.as_dict().items():
        s += w.get(k, 0.0) * v
    return s


def extract(
    tree: Tree,
    rules: ReadabilityRules,
    base_url: str | None = None,
    weights: dict[str, float] | None = None,
) -> DomResult:
    body = tree.body
    if body is None:
        return DomResult()
    w = weights or DEFAULT_WEIGHTS
    cands = iter_candidate_blocks(body)
    texts = [node_text(n) for n, _ in cands]
    feats = compute_features(cands, texts, rules)
    res = DomResult(scored=len(cands))
    if not cands:
        return res
    largest = max(range(len(cands)), key=lambda i: len(texts[i]))
    res.largest_xpath = xpath_of(cands[largest][0])
    raw = [linear_score(f, w) for f in feats]
    # هموارسازی با همسایه‌ها: بلوک کوتاه بین دو بلوک محتوایی، محتواست
    for i, f in enumerate(feats):
        nb = [raw[j] for j in (i - 1, i + 1) if 0 <= j < len(raw)]
        f.neighbor = max(0.0, sum(nb) / len(nb)) if nb else 0.0
    for (node, tag), f in zip(cands, feats, strict=True):
        prob = 1.0 / (1.0 + math.exp(-linear_score(f, w)))
        if prob >= 0.5:
            emit_block(node, tag, base_url, res.blocks, source=SOURCE)
    ensure_h1(body, res.blocks, base_url, source=SOURCE)
    return res
