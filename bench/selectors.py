"""ساخت برچسب خودکار («auto») با selectorهای مخصوص هر سایت — مستقل از استخراج‌گرهای filbert.

متن = `node_text` عناصر `include` (به ترتیب سند، بدون تکرار) پس از حذف `exclude` و تگ‌های غیرمحتوا.
"""

from __future__ import annotations

from filbert.extract.domtext import node_text, parse

_ALWAYS_EXCLUDE = (
    "script, style, noscript, template, iframe, svg, canvas, form, button, input, select, textarea"
)


def gold_from_selectors(html: str, include: list[str], exclude: list[str] | None = None) -> str:
    tree = parse(html)
    for sel in [_ALWAYS_EXCLUDE, *(exclude or [])]:
        for n in tree.css(sel):
            n.decompose()
    seen: set[int] = set()
    chunks: list[str] = []
    for sel in include:
        for n in tree.css(sel):
            # اگر جدِ این نود قبلاً گرفته شده، تکرار نکن
            cur = n
            dup = False
            while cur is not None:
                if cur.mem_id in seen:
                    dup = True
                    break
                cur = cur.parent
            if dup:
                continue
            seen.add(n.mem_id)
            t = node_text(n)
            if t:
                chunks.append(t)
    return "\n\n".join(chunks)
