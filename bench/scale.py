"""تست مقیاس آفلاین: N سند (HTML کش‌شده دیتاست، تکرارشونده) از مسیر کامل استخراج با ProcessPool.

    python -m bench.scale --dataset fa-200 --n 10000 --workers 8

معیار خروج فاز ۴: ≥۳۰۰ صفحه/ثانیه با ۸ پردازه و صفر خطا.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from bench.datasets import Dataset
from filbert.config import Settings
from filbert.pipeline import _extract_job, _worker_init


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fa-200")
    ap.add_argument("--n", type=int, default=10_000)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--chunksize", type=int, default=8)
    args = ap.parse_args()
    ds = Dataset(args.dataset)
    base = [(ds.html(p.id), p.url) for p in ds.pages()]
    jobs = []
    i = 0
    while len(jobs) < args.n:
        html, url = base[i % len(base)]
        jobs.append(
            {
                "html": html,
                "url": f"{url}{'&' if '?' in url else '?'}i={i}",
                "final_url": url,
                "http": {},
                "headers": {},
                "fetched_at": None,
                "raw_html_ref": None,
            }
        )
        i += 1
    settings = Settings(_env_file=None)
    errors = 0
    hashes: set[str] = set()
    t0 = time.perf_counter()
    with ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=_worker_init,
        initargs=(settings.model_dump(mode="json"),),
    ) as ex:
        for rec in ex.map(_extract_job, jobs, chunksize=args.chunksize):
            if rec.error or not rec.content.blocks and rec.content.text == "":
                errors += 1
            if rec.content_hash:
                hashes.add(rec.content_hash)
    dt = time.perf_counter() - t0
    res = {
        "n": len(jobs),
        "workers": args.workers,
        "seconds": round(dt, 1),
        "pages_per_second": round(len(jobs) / dt, 1),
        "errors": errors,
        "distinct_hashes": len(hashes),
    }
    Path("bench/results").mkdir(exist_ok=True)
    Path("bench/results/scale.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res))


if __name__ == "__main__":
    main()
