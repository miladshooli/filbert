"""گام ۴ — رأی‌گیری و ادغام سه استخراج‌گر در سطح بلوک.

- کلید بلوک = XPath + hash متن (`RawBlock.key`).
- ۳ یا ۲ رأی: قطعی. ۱ رأی: فقط اگر از Readability باشد، طول > ۸۰ و بین دو بلوک قطعی (پر کردن حفره).
- ترتیب خروجی = ترتیب سند.
- اگر متن خروجی < `min_text_chars` → حالت recall (اتحاد سه خروجی) و `low_confidence=true`.
- `confidence` = میانگین نسبت رأی بلوک‌های خروجی (votes / تعداد استخراج‌گرها).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from filbert.extract import cetd, domscore, readability
from filbert.extract.blocks import RawBlock, doc_order, join_text
from filbert.extract.domtext import Tree
from filbert.extract.rules import Rules
from filbert.models import Block

EXTRACTORS: tuple[str, ...] = (readability.SOURCE, cetd.SOURCE, domscore.SOURCE)
GAP_FILL_SOURCE = readability.SOURCE
GAP_FILL_MIN_CHARS = 80


@dataclass(slots=True)
class Voted:
    block: RawBlock
    votes: int
    sources: set[str] = field(default_factory=set)
    order: int = 0


@dataclass(slots=True)
class EnsembleResult:
    blocks: list[Block] = field(default_factory=list)
    confidence: float | None = None
    low_confidence: bool = False
    recall_mode: bool = False
    extractors: dict[str, float] = field(default_factory=dict)  # سهم هر استخراج‌گر در خروجی نهایی
    per_extractor_blocks: dict[str, int] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks if b.text)


def run_extractors(tree: Tree, rules: Rules, base_url: str | None) -> dict[str, list[RawBlock]]:
    return {
        readability.SOURCE: readability.extract(tree, rules.readability, base_url).blocks,
        cetd.SOURCE: cetd.extract(tree, base_url).blocks,
        domscore.SOURCE: domscore.extract(tree, rules.readability, base_url).blocks,
    }


def vote(outputs: dict[str, list[RawBlock]], order: dict[int, int]) -> list[Voted]:
    """بلوک‌ها را با کلید ادغام می‌کند و به ترتیب سند برمی‌گرداند."""
    table: dict[str, Voted] = {}
    for source, blocks in outputs.items():
        for b in blocks:
            key = b.key
            v = table.get(key)
            if v is None:
                v = Voted(block=b, votes=0, order=order.get(b.node.mem_id, 10**9))
                table[key] = v
            if source not in v.sources:
                v.sources.add(source)
                v.votes += 1
    return sorted(table.values(), key=lambda v: v.order)


def select(voted: list[Voted], n_extractors: int = len(EXTRACTORS)) -> list[Voted]:
    certain = [v.votes >= 2 for v in voted]
    chosen: list[Voted] = []
    for i, v in enumerate(voted):
        if certain[i]:
            chosen.append(v)
            continue
        if (
            GAP_FILL_SOURCE in v.sources
            and len(v.block.text) > GAP_FILL_MIN_CHARS
            and any(certain[:i])
            and any(certain[i + 1 :])
        ):
            chosen.append(v)
    return chosen


def merge(
    tree: Tree,
    outputs: dict[str, list[RawBlock]],
    *,
    min_text_chars: int = 200,
    recall: bool = False,
) -> EnsembleResult:
    body = tree.body
    res = EnsembleResult(per_extractor_blocks={k: len(v) for k, v in outputs.items()})
    if body is None:
        return res
    voted = vote(outputs, doc_order(body))
    chosen = select(voted)
    text_len = len(join_text([v.block for v in chosen]))
    if recall or text_len < min_text_chars:
        chosen = voted  # اتحاد
        res.recall_mode = True
        res.low_confidence = True
    n = len(outputs) or 1
    res.blocks = [v.block.to_block(votes=v.votes) for v in chosen]
    if chosen:
        res.confidence = round(sum(v.votes for v in chosen) / (n * len(chosen)), 3)
    if len(res.text) < min_text_chars:
        res.low_confidence = True
    for source in outputs:
        if chosen:
            res.extractors[source] = round(
                sum(1 for v in chosen if source in v.sources) / len(chosen), 3
            )
        else:
            res.extractors[source] = 0.0
    return res


def extract(
    tree: Tree,
    rules: Rules,
    base_url: str | None = None,
    *,
    min_text_chars: int = 200,
    recall: bool = False,
) -> EnsembleResult:
    """درخت (پس از preclean) → خروجی ensemble."""
    return merge(
        tree, run_extractors(tree, rules, base_url), min_text_chars=min_text_chars, recall=recall
    )
