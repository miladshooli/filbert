"""اجرای bench: `python -m bench.run --dataset fa-200 --compare-with trafilatura [--check] [--update-baseline]`.

خروجی: `bench/results/<dataset>.json` و `bench/report.md`. با `--check`، افت بیش از 0.5 F1 (×۱۰۰)
یا ۱۰٪ سرعت نسبت به `bench/baseline.json` خطا می‌دهد (قاعده CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from bench import baselines
from bench.datasets import Dataset
from bench.eval import Aggregate, meta_matches, prf
from filbert import __version__
from filbert.config import Settings
from filbert.pipeline import extract_html

log = logging.getLogger("bench")
ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results"
BASELINE_PATH = ROOT / "baseline.json"
REPORT_PATH = ROOT / "report.md"
F1_TOLERANCE = 0.005  # 0.5 امتیاز F1
SPEED_TOLERANCE = 0.10


def run_dataset(ds: Dataset, extractors: dict[str, baselines.Extractor], repeat: int = 1) -> dict:
    aggs = {name: Aggregate(name) for name in extractors}
    meta_agg = Aggregate("pipeline-meta")
    settings = Settings(_env_file=None)
    pages = list(ds.labeled())
    per_page: list[dict] = []
    for page in pages:
        html = ds.html(page.id)
        gold = ds.gold_text(page.id) or ""
        row: dict = {"id": page.id, "type": page.type, "status": page.label_status}
        for name, fn in extractors.items():
            best_ms: float | None = None
            text = ""
            try:
                for _ in range(repeat):
                    t0 = time.perf_counter()
                    text = fn(html, page.url)
                    ms = (time.perf_counter() - t0) * 1000
                    best_ms = ms if best_ms is None else min(best_ms, ms)
            except Exception as e:  # noqa: BLE001
                log.warning("%s failed on %s: %s", name, page.id, e)
                aggs[name].failures += 1
                text = ""
            r = prf(text, gold)
            aggs[name].add(page.type, r, best_ms)
            row[name] = round(r.f1, 4)
        gold_meta = ds.gold_meta(page.id)
        if gold_meta:
            rec = extract_html(html, page.url, settings=settings)
            pred = {
                "title": rec.seo.title,
                "description": rec.seo.description,
                "canonical": rec.canonical,
                "published_at": rec.seo.published_at,
                "author": rec.seo.author,
            }
            meta_agg.add_meta(meta_matches(pred, gold_meta))
        per_page.append(row)
    return {
        "dataset": ds.name,
        "tool_version": __version__,
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_pages": len(pages),
        "label_summary": ds.summary(),
        "extractors": {n: a.summary() for n, a in aggs.items()},
        "meta": meta_agg.summary()["meta"],
        "pages": per_page,
    }


def render_report(results: list[dict]) -> str:
    lines = [
        "# گزارش bench",
        "",
        f"تولید خودکار · filbert {__version__} · {results[0]['at'] if results else ''}",
        "",
    ]
    for res in results:
        lines += [f"## دیتاست `{res['dataset']}` — {res['n_pages']} صفحه برچسب‌دار", ""]
        lines += [
            "| استخراج‌گر | P | R | **F1** | دقت صفحه | p50 ms | p95 ms | خطا |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for n, s in res["extractors"].items():
            lines.append(
                f"| {n} | {s['precision']} | {s['recall']} | **{s['f1']}** | {s['page_accuracy']} | {s['p50_ms']} | {s['p95_ms']} | {s['failures']} |"
            )
        types = sorted({t for s in res["extractors"].values() for t in s["by_type"]})
        if types:
            lines += [
                "",
                "F1 به تفکیک نوع صفحه:",
                "",
                "| استخراج‌گر | " + " | ".join(types) + " |",
                "| --- |" + " --- |" * len(types),
            ]
            for n, s in res["extractors"].items():
                lines.append(
                    f"| {n} | " + " | ".join(str(s["by_type"].get(t, "-")) for t in types) + " |"
                )
        if res["meta"]:
            lines += [
                "",
                "دقت متادیتا (pipeline، exact match): "
                + ", ".join(f"{k}={v}" for k, v in res["meta"].items()),
            ]
        lines += ["", "برچسب‌ها: " + json.dumps(res["label_summary"], ensure_ascii=False), ""]
    return "\n".join(lines)


def check_regression(res: dict, baseline: dict, *, speed: bool = True) -> list[str]:
    problems: list[str] = []
    base = baseline.get(res["dataset"], {})
    for name in ("ensemble", "pipeline"):
        cur, old = res["extractors"].get(name), base.get(name)
        if not cur or not old:
            continue
        if (
            old.get("f1") is not None
            and cur["f1"] is not None
            and cur["f1"] < old["f1"] - F1_TOLERANCE
        ):
            problems.append(f"{res['dataset']}/{name}: F1 {old['f1']} → {cur['f1']}")
        if (
            speed
            and old.get("p50_ms")
            and cur["p50_ms"]
            and cur["p50_ms"] > old["p50_ms"] * (1 + SPEED_TOLERANCE)
        ):
            problems.append(f"{res['dataset']}/{name}: p50 {old['p50_ms']}ms → {cur['p50_ms']}ms")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="filbert bench")
    ap.add_argument(
        "--dataset", action="append", default=None, help="نام دیتاست (چندتایی)؛ پیش‌فرض: همه"
    )
    ap.add_argument("--compare-with", default="", help="خط پایه‌ها با ویرگول، مثلاً trafilatura")
    ap.add_argument("--extractors", default="readability,cetd,dom,ensemble,pipeline")
    ap.add_argument("--repeat", type=int, default=1, help="تکرار برای زمان‌سنجی (کمینه زمان)")
    ap.add_argument("--check", action="store_true", help="مقایسه با baseline.json و خطا در افت")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument(
        "--no-speed-check",
        action="store_true",
        help="فقط F1 را با baseline مقایسه کن (CI با ماشین متفاوت)",
    )
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    names = [n for n in args.extractors.split(",") if n]
    names += [n for n in args.compare_with.split(",") if n]
    extractors = baselines.resolve([n for n in names if n != "pipeline"])
    if "pipeline" in names:
        extractors["pipeline"] = baselines.fb_pipeline

    ds_names = args.dataset or sorted(
        p.name for p in (ROOT / "datasets").iterdir() if (p / "index.jsonl").exists()
    )
    results = []
    for name in ds_names:
        ds = Dataset(name)
        if not ds.exists():
            print(f"dataset not found: {name}", file=sys.stderr)
            return 2
        res = run_dataset(ds, extractors, repeat=args.repeat)
        results.append(res)
        RESULTS_DIR.mkdir(exist_ok=True)
        (RESULTS_DIR / f"{name}.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"[{name}] n={res['n_pages']} "
            + " ".join(
                f"{n}=F1:{s['f1']}/p50:{s['p50_ms']}ms" for n, s in res["extractors"].items()
            )
        )

    if not args.no_report:
        REPORT_PATH.write_text(render_report(results), encoding="utf-8")
    baseline = (
        json.loads(BASELINE_PATH.read_text(encoding="utf-8")) if BASELINE_PATH.exists() else {}
    )
    if args.check:
        problems = [
            p for r in results for p in check_regression(r, baseline, speed=not args.no_speed_check)
        ]
        if problems:
            print("REGRESSION:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        print("check: ok")
    if args.update_baseline:
        for r in results:
            baseline[r["dataset"]] = {
                n: {"f1": s["f1"], "p50_ms": s["p50_ms"]} for n, s in r["extractors"].items()
            }
        BASELINE_PATH.write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"baseline updated: {BASELINE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
