"""ساخت دیتاست از `sources.yml`: کشف URL → دریافت (با کش filbert) → ذخیره HTML → برچسب خودکار با selector.

    python -m bench.collect --dataset fa-200 [--sources a,b] [--dry-run] [--limit N]

برچسب `auto` فقط وقتی متن selector ≥ min_chars باشد؛ وگرنه `unlabeled` (برای برچسب‌زنی دستی با bench.label).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import sys
from pathlib import Path

import yaml

from bench.datasets import Dataset, Page
from bench.discover import discover
from bench.selectors import gold_from_selectors
from filbert.config import Settings
from filbert.extract.domtext import parse
from filbert.fetch.cache import Cache
from filbert.fetch.client import Fetcher, FetchError
from filbert.meta.head import extract_head

log = logging.getLogger("bench.collect")
SOURCES_PATH = Path(__file__).resolve().parent / "sources.yml"


def load_sources(path: Path = SOURCES_PATH) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["sources"]


def page_id(site: str, url: str) -> str:
    return f"{site}-{hashlib.sha256(url.encode()).hexdigest()[:8]}"


async def collect_source(
    src: dict, ds: Dataset, settings: Settings, cache: Cache, limit: int | None, dry_run: bool
) -> dict:
    want = limit or src["count"]
    existing = {p.url for p in ds.pages() if p.site == src["site"]}
    urls = await discover(src, settings, int(want * 1.6) + 2)
    stats = {
        "site": src["site"],
        "discovered": len(urls),
        "added": 0,
        "auto": 0,
        "failed": 0,
        "existing": len(existing),
    }
    if dry_run:
        for u in urls[:want]:
            print(f"  {src['site']}: {u}")
        return stats
    gold = src.get("gold", {})
    added = len(existing)
    async with Fetcher(settings, cache) as f:
        for u in urls:
            if added >= want:
                break
            if u in existing:
                continue
            try:
                r = await f.fetch(u)
            except FetchError as e:
                stats["failed"] += 1
                log.warning("%s: %s", src["site"], e)
                continue
            if "html" not in (r.headers.get("content-type") or "text/html") or len(r.text) < 2000:
                stats["failed"] += 1
                continue
            text = (
                gold_from_selectors(r.text, gold.get("include", []), gold.get("exclude", []))
                if gold
                else ""
            )
            status = "auto" if len(text) >= gold.get("min_chars", 300) else "unlabeled"
            seo = extract_head(parse(r.text), r.final_url)
            pid = page_id(src["site"], r.url)
            page = Page(
                id=pid,
                url=r.url,
                type=src["type"],
                label_status=status,
                site=src["site"],
                extra={
                    "title": seo.title,
                    "final_url": r.final_url,
                    "status": r.status,
                    "html_kb": len(r.text) // 1024,
                    "fetched_at": r.fetched_at.isoformat(timespec="seconds"),
                    "gold_chars": len(text),
                },
            )
            ds.add_page(page, r.text)
            if status == "auto":
                ds.put_gold(
                    pid,
                    text,
                    {
                        "title": seo.title,
                        "canonical": seo.canonical,
                        "description": seo.description,
                    },
                )
                stats["auto"] += 1
            added += 1
            stats["added"] += 1
    return stats


async def main_async(args: argparse.Namespace) -> int:
    settings = Settings(_env_file=None)
    cache = Cache(settings.cache_dir)
    ds = Dataset(args.dataset)
    ds.create()
    sources = load_sources()
    if args.sources:
        wanted = set(args.sources.split(","))
        sources = [s for s in sources if s["site"] in wanted]
    sem = asyncio.Semaphore(args.parallel)

    async def run(src: dict) -> dict:
        async with sem:
            try:
                return await asyncio.wait_for(
                    collect_source(src, ds, settings, cache, args.limit, args.dry_run), args.timeout
                )
            except TimeoutError:
                return {"site": src["site"], "error": "timeout"}
            except Exception as e:  # noqa: BLE001
                log.exception("source %s failed", src["site"])
                return {"site": src["site"], "error": f"{type(e).__name__}: {e}"}

    results = await asyncio.gather(*(run(s) for s in sources))
    for r in results:
        print(r)
    print("summary:", ds.summary())
    cache.close()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fa-200")
    ap.add_argument("--sources", default="", help="فقط این سایت‌ها (با ویرگول)")
    ap.add_argument("--limit", type=int, default=None, help="سقف صفحه برای هر منبع (به‌جای count)")
    ap.add_argument("--parallel", type=int, default=4, help="منابع همزمان (هر منبع یک host)")
    ap.add_argument("--timeout", type=float, default=900, help="سقف ثانیه برای هر منبع")
    ap.add_argument("--dry-run", action="store_true", help="فقط کشف URL")
    ap.add_argument("-v", action="count", default=0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING if args.v == 0 else logging.INFO)
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
