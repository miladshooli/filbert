"""تبدیل برچسب‌های بازبینی انسانی (خروجی ابزار آنلاین: `labels/<id>.json`) به gold دیتاست.

    python -m bench.promote_labels --dataset fa-200

هر سند: {status: gold|unsure|skip, on: [اندیس بلوک‌های کاندید], meta: {...}, note}. اندیس‌ها همان ترتیب
`iter_candidate_blocks` روی درخت خام صفحه‌اند (همان چیزی که ابزار نشان داده).
- gold → gold/<id>.txt و .json بازنویسی، `label_status=gold`
- unsure → برچسب انسانی ذخیره می‌شود ولی وضعیت `auto` می‌ماند (در bench شمرده می‌شود، با پرچم)
- skip → `label_status=rejected` (از bench خارج می‌شود)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bench.datasets import Dataset
from bench.eval import prf
from filbert.extract.blocks import iter_candidate_blocks
from filbert.extract.domtext import node_text, parse


def gold_from_label(html: str, on: list[int]) -> str:
    tree = parse(html)
    cands = iter_candidate_blocks(tree.body)
    want = set(on)
    parts = []
    for i, (node, _tag) in enumerate(cands):
        if i in want:
            t = node_text(node)
            if t:
                parts.append(t)
    return "\n\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fa-200")
    args = ap.parse_args()
    ds = Dataset(args.dataset)
    labels_dir = ds.root / "labels"
    pages = {p.id: p for p in ds.pages()}
    stats = {"gold": 0, "unsure": 0, "skip": 0, "missing": 0}
    deltas = []
    for f in sorted(labels_dir.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        d = doc.get("data", doc)
        pid = d.get("page_id") or f.stem
        page = pages.get(pid)
        if page is None:
            stats["missing"] += 1
            continue
        status = d.get("status", "unsure")
        stats[status] = stats.get(status, 0) + 1
        if status == "skip":
            page.label_status = "rejected"
            page.extra["review"] = {
                "status": "skip",
                "note": d.get("note"),
                "at": d.get("updated_at"),
            }
            continue
        html = ds.html(pid)
        text = gold_from_label(html, d.get("on") or [])
        old = ds.gold_text(pid) or ""
        deltas.append(prf(old, text).f1 if text else 0.0)
        meta = {k: v for k, v in (d.get("meta") or {}).items() if v}
        ds.put_gold(pid, text, meta)
        page.label_status = "gold" if status == "gold" else "auto"
        page.extra["review"] = {
            "status": status,
            "note": d.get("note"),
            "at": d.get("updated_at"),
            "n_on": len(d.get("on") or []),
            "auto_vs_human_f1": round(deltas[-1], 3),
        }
    ds.write_index(list(pages.values()))
    import statistics

    print(
        json.dumps(
            {
                **stats,
                "auto_vs_human_f1_mean": round(statistics.fmean(deltas), 4) if deltas else None,
                "pages_changed_a_lot": sum(1 for x in deltas if x < 0.8),
            },
            ensure_ascii=False,
        )
    )
    print("summary:", ds.summary())
    Path("bench/results").mkdir(exist_ok=True)


if __name__ == "__main__":
    main()
