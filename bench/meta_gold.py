"""gold متادیتای نیمه‌خودکار برای دیتاست: title/description/canonical از head، و published_at/author
از داده ساخت‌یافته خودِ سایت (JSON-LD یا `article:published_time`/`meta[name=author]`) — منبعی که سایت
برای موتور جست‌وجو اعلام کرده. فیلدی که سایت اعلام نکرده در gold نمی‌آید (ارزیابی نمی‌شود).
بازبینی دستی با `bench.label` (فرم متادیتا) انجام می‌شود.

    python -m bench.meta_gold --dataset fa-200
"""

from __future__ import annotations

import argparse

from bench.datasets import Dataset
from filbert.extract.domtext import parse
from filbert.meta import jsonld
from filbert.meta.dates import parse_any
from filbert.meta.head import collect_meta, extract_head
from filbert.meta.social import clean_author


def gold_meta_for(html: str, url: str) -> dict:
    tree = parse(html)
    seo = extract_head(tree, url)
    items = jsonld.extract_jsonld(tree)
    by_name, by_prop, _ = collect_meta(tree)
    meta = {
        k: v
        for k, v in (
            ("title", seo.title),
            ("description", seo.description),
            ("canonical", seo.canonical),
        )
        if v
    }
    raw_date = by_prop.get("article:published_time") or jsonld.date_published(items)
    if raw_date:
        p = parse_any(raw_date, source="gold")
        if p:
            meta["published_at"] = p.iso
    author = clean_author(by_name.get("author")) or clean_author(jsonld.author_name(items))
    if author:
        meta["author"] = author
    return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fa-200")
    ap.add_argument(
        "--overwrite-gold", action="store_true", help="متادیتای صفحات gold را هم بازنویسی کن"
    )
    args = ap.parse_args()
    ds = Dataset(args.dataset)
    n = with_date = with_author = 0
    for page in ds.pages():
        if page.label_status == "gold" and not args.overwrite_gold:
            continue
        meta = gold_meta_for(ds.html(page.id), page.extra.get("final_url") or page.url)
        existing = ds.gold_meta(page.id) or {}
        # مقادیر دستی (کلیدهایی که قبلاً کاربر اصلاح کرده) حفظ می‌شوند
        for k, v in existing.items():
            if k not in meta and v:
                meta[k] = v
        ds.put_gold(page.id, None, meta)
        n += 1
        with_date += "published_at" in meta
        with_author += "author" in meta
    print(f"{n} pages: published_at={with_date} author={with_author}")


if __name__ == "__main__":
    main()
