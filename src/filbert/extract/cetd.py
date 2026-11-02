"""گام ۲ — چگالی متن ترکیبی (CETD؛ Sun, Song, Liao — SIGIR 2011) روی selectolax.

برای هر عنصر: `C` کاراکتر، `T` تگ، `LC` کاراکتر لینک، `LT` تگ لینک (زیردرخت).
    TD  = C / T
    CTD = (C / T) · log_b( (C / LC) · (T / LT) ),   b = ln( (C / NC) · LC + (LC_body / C_body) · C + e )
    DensitySum(node) = Σ CTD(فرزندان)
آستانه = کمینه CTD روی مسیر از نودِ با بیشترین DensitySum تا body. نودهای با CTD ≥ آستانه محتوا
هستند و زیردرختِ فرزندِ با بیشترین DensitySum آن‌ها کامل علامت می‌خورد. همه در یک پیمایش معکوس پیش‌ترتیب.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from filbert.extract.blocks import (
    PageContext,
    RawBlock,
    collect_blocks,
    collect_from_candidates,
    ensure_h1,
    join_text,
)
from filbert.extract.domtext import Node, Tree, xpath_of
from filbert.extract.stats import NodeStats, compute_stats  # noqa: F401 — re-export

SOURCE = "cetd"


@dataclass(slots=True)
class CetdResult:
    blocks: list[RawBlock] = field(default_factory=list)
    threshold: float = 0.0
    max_density_xpath: str | None = None
    marked: int = 0

    @property
    def text(self) -> str:
        return join_text(self.blocks)


def _ctd(s: NodeStats, lc_body: int, c_body: int) -> float:
    c = s.chars
    if c == 0:
        return 0.0
    t = max(1, s.tags)
    lc = max(1, s.link_chars)
    lt = max(1, s.link_tags)
    nc = max(1, c - s.link_chars)
    base = math.log((c / nc) * lc + (lc_body / max(1, c_body)) * c + math.e)
    arg = (c / lc) * (t / lt)
    if base <= 0 or arg <= 1:
        return c / t
    return (c / t) * math.log(arg) / base


def score(body: Node, stats: dict[int, NodeStats]) -> None:
    """CTD و DensitySum را درجا پر می‌کند."""
    b = stats.get(body.mem_id, NodeStats())
    for s in stats.values():
        s.ctd = _ctd(s, b.link_chars, b.chars)
    for n in body.traverse():
        s = stats.get(n.mem_id)
        if s is None:
            continue
        child = n.child
        total = 0.0
        while child is not None:
            cs = stats.get(child.mem_id)
            if cs is not None and child.is_element_node:
                total += cs.ctd
            child = child.next
        s.density_sum = total


def _max_density_node(body: Node, stats: dict[int, NodeStats]) -> Node:
    best, best_v = body, -1.0
    for n in body.traverse():
        s = stats.get(n.mem_id)
        if s is not None and n.is_element_node and s.density_sum > best_v:
            best, best_v = n, s.density_sum
    return best


def _threshold(node: Node, body: Node, stats: dict[int, NodeStats]) -> float:
    thr = float("inf")
    cur: Node | None = node
    while cur is not None:
        s = stats.get(cur.mem_id)
        if s is not None:
            thr = min(thr, s.ctd)
        if cur.mem_id == body.mem_id:
            break
        cur = cur.parent
    return 0.0 if thr == float("inf") else thr


def _find_max_density_sum(node: Node, stats: dict[int, NodeStats]) -> Node:
    """در زیردرخت، فرزندِ با بیشترین DensitySum را به‌صورت بازگشتی دنبال می‌کند."""
    cur = node
    while True:
        best, best_v = None, stats.get(cur.mem_id, NodeStats()).density_sum
        child = cur.child
        while child is not None:
            cs = stats.get(child.mem_id)
            if cs is not None and child.is_element_node and cs.density_sum > best_v:
                best, best_v = child, cs.density_sum
            child = child.next
        if best is None:
            return cur
        cur = best


def mark_content(body: Node, stats: dict[int, NodeStats], threshold: float) -> set[int]:
    marked: set[int] = set()

    def mark_subtree(n: Node) -> None:
        for d in n.traverse():
            if d.is_element_node:
                marked.add(d.mem_id)

    def walk(n: Node) -> None:
        child = n.child
        while child is not None:
            if child.is_element_node and child.mem_id not in marked:
                s = stats.get(child.mem_id)
                if s is not None and s.ctd >= threshold and s.chars > 0:
                    mark_subtree(_find_max_density_sum(child, stats))
                walk(child)
            child = child.next

    walk(body)
    return marked


def extract(tree: Tree, base_url: str | None = None, ctx: PageContext | None = None) -> CetdResult:
    body = tree.body
    if body is None:
        return CetdResult()
    stats = ctx.stats if (ctx is not None and ctx.stats is not None) else compute_stats(body)
    if ctx is not None and ctx.stats is None:
        ctx.stats = stats
    if stats.get(body.mem_id, NodeStats()).chars == 0:
        return CetdResult()
    score(body, stats)
    max_node = _max_density_node(body, stats)
    thr = _threshold(max_node, body, stats)
    marked = mark_content(body, stats, thr)
    res = CetdResult(
        threshold=round(thr, 3), max_density_xpath=xpath_of(max_node), marked=len(marked)
    )

    def is_marked(n: Node) -> bool:
        cur: Node | None = n
        while cur is not None and cur.mem_id != body.mem_id:
            if cur.mem_id in marked:
                return True
            cur = cur.parent
        return False

    if ctx is not None:
        collect_from_candidates(ctx, body, base_url, res.blocks, source=SOURCE, predicate=is_marked)
    else:
        collect_blocks(body, base_url, res.blocks, source=SOURCE, predicate=is_marked)
    ensure_h1(body, res.blocks, base_url, source=SOURCE, ctx=ctx)
    return res
