"""ساخت داده‌های ابزار بازبینی آنلاین (Artifact) از یک دیتاست: index.json + data/sites/<site>.json.

python -m bench.review_export --dataset fa-biz-100 --out /path/to/review/data
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bench.datasets import Dataset
from filbert.extract.blocks import iter_candidate_blocks
from filbert.extract.domtext import node_text, parse, xpath_of
from filbert.meta.head import extract_head


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fa-200")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    ds = Dataset(args.dataset)
    out = Path(args.out)
    (out / "sites").mkdir(parents=True, exist_ok=True)
    index, by_site = [], {}
    for p in ds.pages():
        html = ds.html(p.id)
        tree = parse(html)
        seo = extract_head(tree, p.url)
        gold = ds.gold_text(p.id) or ""
        gold_meta = ds.gold_meta(p.id) or {}
        blocks = []
        for i, (node, tag) in enumerate(iter_candidate_blocks(tree.body)):
            text = node_text(node)
            if len(text) < 2:
                continue
            blocks.append(
                {
                    "i": i,
                    "tag": tag,
                    "xpath": xpath_of(node),
                    "text": text[:1500],
                    "on": bool(text and text[:200] in gold),
                }
            )
        page = {
            "id": p.id,
            "url": p.url,
            "type": p.type,
            "site": p.site,
            "status": p.label_status,
            "title": seo.title,
            "sector": p.extra.get("sector"),
            "meta": {
                "title": gold_meta.get("title", seo.title),
                "description": gold_meta.get("description", seo.description),
                "canonical": gold_meta.get("canonical", seo.canonical),
                "published_at": gold_meta.get("published_at"),
                "author": gold_meta.get("author"),
            },
            "blocks": blocks,
        }
        by_site.setdefault(p.site, []).append(page)
        index.append(
            {
                "id": p.id,
                "type": p.type,
                "site": p.site,
                "status": p.label_status,
                "title": seo.title or p.url,
                "n_blocks": len(blocks),
                "n_on": sum(b["on"] for b in blocks),
            }
        )
    for site, pages in by_site.items():
        (out / "sites" / f"{site}.json").write_text(
            json.dumps(sorted(pages, key=lambda x: x["id"]), ensure_ascii=False), encoding="utf-8"
        )
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(f"{len(index)} pages, {len(by_site)} sites → {out}")
    print(" ".join(sorted(f"data/sites/{s}.json" for s in by_site)))


if __name__ == "__main__":
    main()
