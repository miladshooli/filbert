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
from filbert.extract.domtext import Node, Tree
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
    raw_blocks: list[RawBlock] = field(default_factory=list)  # با ارجاع به نود؛ برای in_main ساختار
    confidence: float | None = None
    low_confidence: bool = False
    recall_mode: bool = False
    recall_anchor: bool = False  # رأی‌گیری خیلی کم داد؛ خروجی CETD ∪ اکثریت (صفحات فهرستی/مشخصات)
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


def _ancestor_ids(node: Node, stop_id: int) -> list[int]:
    ids: list[int] = []
    cur = node.parent
    while cur is not None and cur.mem_id != stop_id:
        ids.append(cur.mem_id)
        cur = cur.parent
    return ids


def vote(
    outputs: dict[str, list[RawBlock]], order: dict[int, int], body_id: int | None = None
) -> list[Voted]:
    """بلوک‌ها را با کلید ادغام می‌کند و به ترتیب سند برمی‌گرداند.

    رأی با آگاهی از دربرگیری: اگر استخراج‌گری جدِ یک بلوک را (مثلاً کل `ul`) داده باشد، آن بلوک ریز
    هم رأی او را می‌گیرد؛ وگرنه اختلاف granularity رأی‌ها را پخش می‌کند.
    """
    emitted: dict[str, set[int]] = {
        src: {b.node.mem_id for b in blocks} for src, blocks in outputs.items()
    }
    table: dict[str, Voted] = {}
    for source, blocks in outputs.items():
        for b in blocks:
            key = b.key
            v = table.get(key)
            if v is None:
                v = Voted(block=b, votes=0, order=order.get(b.node.mem_id, 10**9))
                table[key] = v
            v.sources.add(source)
    stop = body_id if body_id is not None else -1
    for v in table.values():
        chain = _ancestor_ids(v.block.node, stop)
        for src, ids in emitted.items():
            if src not in v.sources and any(a in ids for a in chain):
                v.sources.add(src)
        v.votes = len(v.sources)
    return sorted(table.values(), key=lambda v: v.order)


def drop_containers(chosen: list[Voted], body_id: int, coverage: float = 0.6) -> list[Voted]:
    """اگر بلوک درشت (مثلاً `ul`) و بلوک‌های ریز داخلش هر دو انتخاب شده‌اند:
    ریزها ≥ ۶۰٪ متن ظرف را پوشش دهند → ظرف حذف؛ وگرنه ریزها حذف و ظرف می‌ماند (مثلاً فهرست مشخصات)."""
    by_id = {v.block.node.mem_id: v for v in chosen}
    covered: dict[int, int] = {}
    inner_of: dict[int, list[int]] = {}
    for v in chosen:
        for a in _ancestor_ids(v.block.node, body_id):
            if a in by_id:
                covered[a] = covered.get(a, 0) + len(v.block.text)
                inner_of.setdefault(a, []).append(v.block.node.mem_id)
                break  # فقط نزدیک‌ترین ظرفِ انتخاب‌شده
    drop: set[int] = set()
    for a, chars in covered.items():
        container_len = max(1, len(by_id[a].block.text))
        if chars / container_len >= coverage:
            drop.add(a)
        else:
            drop.update(inner_of[a])
    return [v for v in chosen if v.block.node.mem_id not in drop]


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


ANCHOR_RATIO = 0.5  # اگر متن اکثریت < ۵۰٪ متن CETD بود، CETD ∪ اکثریت


def merge(
    tree: Tree,
    outputs: dict[str, list[RawBlock]],
    *,
    min_text_chars: int = 200,
    recall: bool = False,
    anchor_ratio: float = ANCHOR_RATIO,
) -> EnsembleResult:
    body = tree.body
    res = EnsembleResult(per_extractor_blocks={k: len(v) for k, v in outputs.items()})
    if body is None:
        return res
    voted = vote(outputs, doc_order(body), body.mem_id)
    chosen = drop_containers(select(voted), body.mem_id)
    text_len = len(join_text([v.block for v in chosen]))
    anchor = cetd.SOURCE
    if anchor in outputs and not recall:
        anchor_len = len(join_text(outputs[anchor]))
        if anchor_len and text_len < anchor_ratio * anchor_len:
            # صفحات فهرستی (مشخصات محصول، پست‌های کوتاه انجمن): Readability/DOM کم می‌آورند؛ CETD لنگر می‌شود
            chosen = drop_containers(
                [v for v in voted if anchor in v.sources or v.votes >= 2], body.mem_id
            )
            text_len = len(join_text([v.block for v in chosen]))
            res.recall_anchor = True
    if recall or text_len < min_text_chars:
        chosen = drop_containers(voted, body.mem_id)  # اتحاد
        res.recall_mode = True
        res.low_confidence = True
    n = len(outputs) or 1
    res.blocks = [v.block.to_block(votes=v.votes) for v in chosen]
    res.raw_blocks = [v.block for v in chosen]
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
