"""گزارش کیفیت چانکینگ روی دیتاست: توزیع اندازه، درصد پایان روی مرز جمله، برش داخل جدول/کد، مسیر هدینگ.

python -m bench.chunk_report --dataset fa-200
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from bench.datasets import Dataset
from filbert.chunk.sentence import ends_at_boundary
from filbert.config import Settings
from filbert.pipeline import extract_html


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fa-200")
    args = ap.parse_args()
    ds = Dataset(args.dataset)
    settings = Settings(_env_file=None)
    sizes: list[int] = []
    boundary_ok = punct_ok = over_hard = 0
    with_path = 0
    zwnj_edge = 0
    n_pages = 0
    by_type: dict[str, list[int]] = {}
    for page in ds.pages():
        rec = extract_html(ds.html(page.id), page.url, settings=settings)
        if not rec.content.chunks:
            continue
        n_pages += 1
        by_type.setdefault(page.type, []).append(len(rec.content.chunks))
        for ch in rec.content.chunks:
            sizes.append(ch.word_count)
            boundary_ok += ends_at_boundary(ch.text_raw) or any(
                t in ch.block_types for t in ("table", "pre", "ul", "ol", "figure")
            )
            punct_ok += ends_at_boundary(ch.text_raw)
            over_hard += ch.word_count > settings.chunk_hard_max
            with_path += bool(ch.heading_path)
            zwnj_edge += ch.text.startswith("‌") or ch.text.endswith("‌")
    s = sorted(sizes)
    q = lambda p: s[min(len(s) - 1, int(len(s) * p))] if s else 0  # noqa: E731
    res = {
        "pages": n_pages,
        "chunks": len(sizes),
        "chunks_per_page_mean": round(len(sizes) / n_pages, 2) if n_pages else 0,
        "words_p10_p50_p90_max": [q(0.1), q(0.5), q(0.9), s[-1] if s else 0],
        "words_mean": round(statistics.fmean(sizes), 1) if sizes else 0,
        "block_or_sentence_boundary_pct": round(100 * boundary_ok / len(sizes), 2)
        if sizes
        else None,
        "ends_with_punctuation_pct": round(100 * punct_ok / len(sizes), 2) if sizes else None,
        "over_hard_max": over_hard,
        "with_heading_path_pct": round(100 * with_path / len(sizes), 1) if sizes else None,
        "zwnj_at_edge": zwnj_edge,
        "chunks_per_page_by_type": {
            t: round(statistics.fmean(v), 1) for t, v in sorted(by_type.items())
        },
    }
    Path("bench/results").mkdir(exist_ok=True)
    Path("bench/results/chunks.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
