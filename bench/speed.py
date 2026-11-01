"""سنجش سرعت روی HTML کش‌شده (بدون شبکه): p50/p95 هر استخراج‌گر و throughput با ۱/۴/۸ پردازه.

python -m bench.speed --dataset fa-200 [--procs 1,4,8] [--repeat 2]
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import tracemalloc
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from bench import baselines
from bench.datasets import Dataset
from filbert.config import Settings
from filbert.pipeline import extract_html

_SETTINGS = Settings(_env_file=None)


def _one(args: tuple[str, str]) -> float:
    html, url = args
    t0 = time.perf_counter()
    extract_html(html, url, settings=_SETTINGS)
    return (time.perf_counter() - t0) * 1000


def per_extractor(pages: list[tuple[str, str]], repeat: int) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, fn in {**baselines.FILBERT, "pipeline": baselines.fb_pipeline}.items():
        times: list[float] = []
        for html, url in pages:
            best = None
            for _ in range(repeat):
                t0 = time.perf_counter()
                fn(html, url)
                ms = (time.perf_counter() - t0) * 1000
                best = ms if best is None else min(best, ms)
            times.append(best or 0.0)
        s = sorted(times)
        out[name] = {
            "p50_ms": round(statistics.median(s), 2),
            "p95_ms": round(s[max(0, int(len(s) * 0.95) - 1)], 2),
            "max_ms": round(s[-1], 2),
        }
    return out


def throughput(pages: list[tuple[str, str]], procs: list[int]) -> dict[int, float]:
    out: dict[int, float] = {}
    for n in procs:
        t0 = time.perf_counter()
        if n == 1:
            for p in pages:
                _one(p)
        else:
            with ProcessPoolExecutor(max_workers=n) as ex:
                list(ex.map(_one, pages, chunksize=4))
        out[n] = round(len(pages) / (time.perf_counter() - t0), 1)
    return out


def peak_memory_mb(pages: list[tuple[str, str]]) -> float:
    biggest = max(pages, key=lambda p: len(p[0]))
    tracemalloc.start()
    extract_html(biggest[0], biggest[1], settings=_SETTINGS)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return round(peak / 1024 / 1024, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fa-200")
    ap.add_argument("--procs", default="1,4,8")
    ap.add_argument("--repeat", type=int, default=2)
    args = ap.parse_args()
    ds = Dataset(args.dataset)
    pages = [(ds.html(p.id), p.url) for p in ds.pages()]
    sizes = sorted(len(h) for h, _ in pages)
    res = {
        "dataset": ds.name,
        "n": len(pages),
        "html_kb_median": sizes[len(sizes) // 2] // 1024 if sizes else 0,
        "per_extractor": per_extractor(pages, args.repeat),
        "pages_per_second": throughput(pages, [int(x) for x in args.procs.split(",")]),
        "peak_mb_largest_page": peak_memory_mb(pages) if pages else None,
    }
    Path("bench/results").mkdir(exist_ok=True)
    Path(f"bench/results/speed-{ds.name}.json").write_text(
        json.dumps(res, indent=2), encoding="utf-8"
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
