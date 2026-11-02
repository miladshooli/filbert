"""آموزش مدل lightgbm برای DOM-scorer روی برچسب‌های fa-200 (gold/auto) با cross-validation به تفکیک سایت.

    python -m bench.train_dom --dataset fa-200 [--save data/models/dom_lgbm.txt]

برچسب بلوک: ≥۸۰٪ توکن‌های بلوک در متن gold باشند (و ≥۳ توکن). ارزیابی اصلی **end-to-end**: F1 ensemble روی
سایت‌های دیده‌نشده (GroupKFold) در برابر وزن‌های دستی. مدل فقط اگر ensemble را بهتر کند ذخیره می‌شود.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path

from bench.datasets import Dataset
from bench.eval import prf, tokens
from filbert.extract import domscore, ensemble
from filbert.extract.blocks import PageContext
from filbert.extract.domtext import parse
from filbert.extract.preclean import preclean
from filbert.extract.rules import load_rules

RULES = load_rules()


def page_examples(html: str, url: str, gold: str) -> tuple[list[list[float]], list[int]]:
    tree = parse(html)
    preclean(tree, RULES.preclean)
    body = tree.body
    if body is None:
        return [], []
    ctx = PageContext.build(body)
    cands = ctx.candidates(body)
    texts = [ctx.node_text(n) for n, _ in cands]
    feats = domscore.compute_features(cands, texts, RULES.readability, ctx)
    raw = [domscore.linear_score(f, domscore.DEFAULT_WEIGHTS) for f in feats]
    for i, f in enumerate(feats):
        nb = [raw[j] for j in (i - 1, i + 1) if 0 <= j < len(raw)]
        f.neighbor = max(0.0, sum(nb) / len(nb)) if nb else 0.0
    gold_counts = Counter(tokens(gold))
    X, y = [], []
    for f, t in zip(feats, texts, strict=True):
        toks = tokens(t)
        if len(toks) < 3:
            continue
        tc = Counter(toks)
        hit = sum(min(c, gold_counts.get(w, 0)) for w, c in tc.items())
        y.append(1 if hit / len(toks) >= 0.8 else 0)
        X.append([getattr(f, k) for k in domscore.FEATURE_ORDER])
    return X, y


def ensemble_f1(ds: Dataset, pages: list, model: domscore.DomModel | None) -> float:
    scores = []
    for p in pages:
        gold = ds.gold_text(p.id) or ""
        tree = parse(ds.html(p.id))
        preclean(tree, RULES.preclean)
        res = ensemble.extract(tree, RULES, p.url, dom_model=model)
        scores.append(prf(res.text, gold).f1)
    return statistics.fmean(scores) if scores else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="fa-200")
    ap.add_argument("--save", default="data/models/dom_lgbm.txt")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--force-save", action="store_true")
    args = ap.parse_args()
    import numpy as np

    try:
        import lightgbm as lgb

        def fit(X, y):
            return lgb.train(
                params, lgb.Dataset(np.array(X), label=np.array(y)), num_boost_round=300
            )

        backend = "lightgbm"
    except (ImportError, OSError):  # روی macOS بدون libomp
        from sklearn.ensemble import HistGradientBoostingClassifier

        def fit(X, y):
            return HistGradientBoostingClassifier(
                learning_rate=0.05,
                max_iter=300,
                max_leaf_nodes=15,
                min_samples_leaf=20,
                random_state=7,
            ).fit(np.array(X), np.array(y))

        backend = "sklearn-hgb"

    ds = Dataset(args.dataset)
    pages = list(ds.labeled())
    data = {}
    for p in pages:
        X, y = page_examples(ds.html(p.id), p.url, ds.gold_text(p.id) or "")
        data[p.id] = (X, y)
    sites = sorted({p.site for p in pages})
    folds = [sites[i :: args.folds] for i in range(args.folds)]
    params = {
        "objective": "binary",
        "learning_rate": 0.05,
        "num_leaves": 15,
        "min_data_in_leaf": 20,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.9,
        "bagging_freq": 1,
        "verbose": -1,
        "seed": 7,
    }
    base_f1, model_f1, aucs = [], [], []
    for hold in folds:
        train_pages = [p for p in pages if p.site not in hold]
        test_pages = [p for p in pages if p.site in hold]
        Xtr = [x for p in train_pages for x in data[p.id][0]]
        ytr = [v for p in train_pages for v in data[p.id][1]]
        booster = fit(Xtr, ytr)
        Xte = [x for p in test_pages for x in data[p.id][0]]
        yte = [v for p in test_pages for v in data[p.id][1]]
        if Xte and len(set(yte)) > 1:
            from sklearn.metrics import roc_auc_score  # type: ignore[import-not-found]

            m0 = domscore.DomModel(booster)
            probs = (
                m0.booster.predict_proba(np.array(Xte))[:, 1]
                if hasattr(booster, "predict_proba")
                else booster.predict(np.array(Xte))
            )
            aucs.append(roc_auc_score(yte, probs))
        m = domscore.DomModel(booster)
        base_f1.append(ensemble_f1(ds, test_pages, None))
        model_f1.append(ensemble_f1(ds, test_pages, m))
        print(
            f"fold {hold}: ensemble F1 base={base_f1[-1]:.4f} model={model_f1[-1]:.4f} (n={len(test_pages)})"
        )
    base, mod = statistics.fmean(base_f1), statistics.fmean(model_f1)
    report = {
        "backend": backend,
        "folds": args.folds,
        "n_pages": len(pages),
        "ensemble_f1_hand_weights": round(base, 4),
        "ensemble_f1_lgbm_cv": round(mod, 4),
        "block_auc_cv": round(statistics.fmean(aucs), 4) if aucs else None,
    }
    print(json.dumps(report, ensure_ascii=False))
    Path("bench/results").mkdir(exist_ok=True)
    Path("bench/results/train_dom.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if mod > base + 0.002 or args.force_save:
        Xall = [x for p in pages for x in data[p.id][0]]
        yall = [v for p in pages for v in data[p.id][1]]
        booster = fit(Xall, yall)
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        if backend != "lightgbm":
            out = out.with_suffix(".pkl")
            import joblib

            joblib.dump(booster, out)
        else:
            booster.save_model(str(out))
        out.with_suffix(".json").write_text(
            json.dumps(
                {"threshold": 0.5, "features": list(domscore.FEATURE_ORDER), **report}, indent=2
            ),
            encoding="utf-8",
        )
        print(f"saved {out} (adopt: ensemble {base:.4f} → {mod:.4f})")
    else:
        print(f"not saved: lgbm does not beat hand weights end-to-end ({base:.4f} vs {mod:.4f})")
    if not math.isfinite(mod):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
