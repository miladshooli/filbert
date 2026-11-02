"""آمار یک‌باره هر عنصر (یک پیمایش معکوس پیش‌ترتیب): کاراکتر، تگ، کاراکتر/تگ لینک.

CETD این‌ها را برای چگالی می‌خواهد؛ Readability و DOM-scorer هم برای طول متن و چگالی لینک.
یک بار در `PageContext` محاسبه و بین سه استخراج‌گر مشترک می‌شود.
"""

from __future__ import annotations

from dataclasses import dataclass

from filbert.extract.domtext import Node


@dataclass(slots=True)
class NodeStats:
    chars: int = 0
    tags: int = 0
    link_chars: int = 0
    link_tags: int = 0
    ctd: float = 0.0
    density_sum: float = 0.0


def compute_stats(body: Node) -> dict[int, NodeStats]:
    """C/T/LC/LT برای هر عنصر در یک پیمایش معکوس پیش‌ترتیب (نوادگان قبل از اجداد)."""
    nodes = list(body.traverse(include_text=True))
    stats: dict[int, NodeStats] = {}
    in_link: dict[int, bool] = {body.mem_id: body.tag == "a"}
    for n in nodes[1:]:
        p = n.parent
        in_link[n.mem_id] = (p is not None and in_link.get(p.mem_id, False)) or n.tag == "a"
    for n in reversed(nodes):
        p = n.parent
        if n.is_text_node:
            if p is None:
                continue
            c = len((n.text_content or "").strip())
            if c == 0:
                continue
            ps = stats.setdefault(p.mem_id, NodeStats())
            ps.chars += c
            if in_link.get(n.mem_id, False):
                ps.link_chars += c
            continue
        if not n.is_element_node:
            continue
        s = stats.setdefault(n.mem_id, NodeStats())
        if p is not None and n.mem_id != body.mem_id:
            ps = stats.setdefault(p.mem_id, NodeStats())
            ps.chars += s.chars
            ps.link_chars += s.link_chars
            ps.tags += s.tags + 1
            ps.link_tags += s.link_tags + (1 if n.tag == "a" else 0)
    return stats
