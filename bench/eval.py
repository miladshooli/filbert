"""معیارها: P/R/F1 توکن‌سطح (difflib روی توکن‌های نرمال‌شده — روش article-extraction-benchmark)،
دقت صفحه (F1 > 0.9)، دقت فیلدی متادیتا (exact match پس از strip)، و آمار سرعت."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from filbert.fa.normalize import normalize_text
from filbert.fa.tokenize import tokenize

META_FIELDS: tuple[str, ...] = ("title", "description", "canonical", "published_at", "author")


def tokens(text: str) -> list[str]:
    return tokenize(normalize_text(text or "", digits="en"))


@dataclass(slots=True)
class PRF:
    precision: float
    recall: float
    f1: float
    n_pred: int
    n_gold: int


def prf(pred_text: str, gold_text: str) -> PRF:
    p, g = tokens(pred_text), tokens(gold_text)
    if not p and not g:
        return PRF(1.0, 1.0, 1.0, 0, 0)
    if not p or not g:
        return PRF(0.0, 0.0, 0.0, len(p), len(g))
    sm = SequenceMatcher(None, p, g, autojunk=False)
    matched = sum(size for _, _, size in sm.get_matching_blocks())
    precision = matched / len(p)
    recall = matched / len(g)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return PRF(precision, recall, f1, len(p), len(g))


def _norm_meta(v: object) -> str | None:
    if v is None:
        return None
    s = " ".join(str(v).split()).strip()
    return s or None


def meta_matches(pred: dict, gold: dict) -> dict[str, bool | None]:
    """None = فیلد در gold نیست (ارزیابی نمی‌شود)."""
    out: dict[str, bool | None] = {}
    for f in META_FIELDS:
        if f not in gold:
            out[f] = None
            continue
        out[f] = _norm_meta(pred.get(f)) == _norm_meta(gold.get(f))
    return out


@dataclass(slots=True)
class Aggregate:
    name: str
    f1s: list[float] = field(default_factory=list)
    precisions: list[float] = field(default_factory=list)
    recalls: list[float] = field(default_factory=list)
    times_ms: list[float] = field(default_factory=list)
    by_type: dict[str, list[float]] = field(default_factory=dict)
    meta_hits: dict[str, list[bool]] = field(default_factory=dict)
    failures: int = 0

    def add(self, page_type: str, r: PRF, ms: float | None) -> None:
        self.f1s.append(r.f1)
        self.precisions.append(r.precision)
        self.recalls.append(r.recall)
        self.by_type.setdefault(page_type, []).append(r.f1)
        if ms is not None:
            self.times_ms.append(ms)

    def add_meta(self, matches: dict[str, bool | None]) -> None:
        for k, v in matches.items():
            if v is not None:
                self.meta_hits.setdefault(k, []).append(v)

    @property
    def n(self) -> int:
        return len(self.f1s)

    def mean(self, xs: list[float]) -> float | None:
        return round(statistics.fmean(xs), 4) if xs else None

    def summary(self) -> dict:
        times = sorted(self.times_ms)
        return {
            "name": self.name,
            "n": self.n,
            "precision": self.mean(self.precisions),
            "recall": self.mean(self.recalls),
            "f1": self.mean(self.f1s),
            "page_accuracy": round(sum(f > 0.9 for f in self.f1s) / self.n, 4) if self.n else None,
            "by_type": {t: round(statistics.fmean(v), 4) for t, v in sorted(self.by_type.items())},
            "meta": {k: round(sum(v) / len(v), 4) for k, v in sorted(self.meta_hits.items()) if v},
            "p50_ms": round(statistics.median(times), 2) if times else None,
            "p95_ms": round(times[max(0, int(len(times) * 0.95) - 1)], 2) if times else None,
            "failures": self.failures,
        }
