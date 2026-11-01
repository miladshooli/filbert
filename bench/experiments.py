"""آزمایش استراتژی‌های ادغام روی دیتاست: به‌ازای هر صفحه خروجی سه استخراج‌گر محاسبه و چند fusion مقایسه می‌شود.

python -m bench.experiments --dataset fa-200
"""

from __future__ import annotations

import argparse
import statistics
from collections import defaultdict

from bench.datasets import Dataset
from bench.eval import prf
from filbert.extract import ensemble
from filbert.extract.blocks import RawBlock, doc_order, join_text
from filbert.extract.domtext import parse
from filbert.extract.preclean import preclean
from filbert.extract.rules import load_rules

RULES = load_rules()


def outputs(html: str, url: str):
    tree = parse(html)
    preclean(tree, RULES.preclean)
    outs = ensemble.run_extractors(tree, RULES, url)
    return tree, outs


def medoid(outs: dict[str, list[RawBlock]]) -> str:
    texts = {k: join_text(v) for k, v in outs.items()}
    best, best_s = None, -1.0
    for k, t in texts.items():
        s = statistics.fmean(prf(t, texts[o]).f1 for o in texts if o != k)
        if s > best_s:
            best, best_s = k, s
    return best or "readability"


def strategies(tree, outs: dict[str, list[RawBlock]]) -> dict[str, str]:
    body = tree.body
    order = doc_order(body)
    voted = ensemble.vote(outs, order, body.mem_id)
    majority = ensemble.drop_containers(ensemble.select(voted), body.mem_id)
    union = ensemble.drop_containers(voted, body.mem_id)
    med = medoid(outs)
    med_keys = {b.key for b in outs[med]}
    med_blocks = [v for v in voted if v.block.key in med_keys or med in v.sources]
    med_plus = ensemble.drop_containers(
        [v for v in voted if (med in v.sources) or v.votes >= 2], body.mem_id
    )
    # وزن‌دار: readability 1.0, cetd 1.2, dom 0.8 — آستانه 1.5
    w = {"readability": 1.0, "cetd": 1.2, "dom": 0.8}
    weighted = ensemble.drop_containers(
        [v for v in voted if sum(w[s] for s in v.sources) >= 1.5], body.mem_id
    )
    maj_text = join_text([v.block for v in majority])
    cetd_text = join_text(outs["cetd"])
    cetd_union = ensemble.drop_containers(
        [v for v in voted if "cetd" in v.sources or v.votes >= 2], body.mem_id
    )
    adaptive: dict[str, str] = {}
    for ratio in (0.4, 0.5, 0.6, 0.7):
        adaptive[f"adaptive@{ratio}"] = (
            join_text([v.block for v in cetd_union])
            if len(maj_text) < ratio * len(cetd_text)
            else maj_text
        )
    res = {
        "majority": maj_text,
        **adaptive,
        "cetd+majority": join_text([v.block for v in cetd_union]),
        "union": join_text([v.block for v in union]),
        "medoid": join_text([v.block for v in ensemble.drop_containers(med_blocks, body.mem_id)]),
        "medoid+majority": join_text([v.block for v in med_plus]),
        "weighted": join_text([v.block for v in weighted]),
    }
    for k, v in outs.items():
        res[k] = join_text(v)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fa-200")
    args = ap.parse_args()
    ds = Dataset(args.dataset)
    scores: dict[str, list[float]] = defaultdict(list)
    by_type: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    oracle: list[float] = []
    for page in ds.labeled():
        gold = ds.gold_text(page.id) or ""
        tree, outs = outputs(ds.html(page.id), page.url)
        res = strategies(tree, outs)
        f1s = {k: prf(v, gold).f1 for k, v in res.items()}
        for k, f in f1s.items():
            scores[k].append(f)
            by_type[page.type][k].append(f)
        oracle.append(max(f1s[k] for k in ("readability", "cetd", "dom")))
    print(f"{'strategy':18s} " + " ".join(f"{t:>8s}" for t in sorted(by_type)) + "   overall")
    for k in sorted(scores, key=lambda k: -statistics.fmean(scores[k])):
        row = " ".join(f"{statistics.fmean(by_type[t][k]):8.3f}" for t in sorted(by_type))
        print(f"{k:18s} {row}   {statistics.fmean(scores[k]):.3f}")
    print(f"{'oracle(best-of-3)':18s} {'':>8s}   {statistics.fmean(oracle):.3f}")


if __name__ == "__main__":
    main()
