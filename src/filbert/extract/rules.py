"""بارگذاری `boilerplate_fa.yml` و کامپایل regexها (یک بار به‌ازای هر مسیر)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "boilerplate_fa.yml"


@dataclass(frozen=True, slots=True)
class PrecleanRules:
    remove_tags: frozenset[str]
    protected_tags: frozenset[str]
    negative: re.Pattern[str]
    maybe_candidate: re.Pattern[str]
    ui_phrases: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ReadabilityRules:
    positive: re.Pattern[str]
    negative: re.Pattern[str]
    class_weight: float = 25.0
    tag_scores: dict[str, float] = field(default_factory=dict)
    min_paragraph_chars: int = 25
    sibling_threshold_ratio: float = 0.2
    sibling_threshold_min: float = 10.0


@dataclass(frozen=True, slots=True)
class Rules:
    preclean: PrecleanRules
    readability: ReadabilityRules
    source: Path


def _norm_phrase(s: str) -> str:
    return " ".join(str(s).replace("\u200c", " ").split()).lower().rstrip(":：؛ ").strip()


def _rx(parts: str | list[str]) -> re.Pattern[str]:
    if isinstance(parts, list):
        parts = "|".join(f"(?:{p})" for p in parts)
    return re.compile(parts, re.IGNORECASE)


@lru_cache(maxsize=8)
def load_rules(path: Path | None = None) -> Rules:
    p = Path(path) if path else DEFAULT_RULES_PATH
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    pc = data["preclean"]
    rd = data["readability"]
    return Rules(
        preclean=PrecleanRules(
            remove_tags=frozenset(pc["remove_tags"]),
            protected_tags=frozenset(pc.get("protected_tags", ["html", "body"])),
            negative=_rx(pc["negative_patterns"]),
            maybe_candidate=_rx(pc["maybe_candidate"]),
            ui_phrases=frozenset(_norm_phrase(x) for x in pc.get("ui_phrases", [])),
        ),
        readability=ReadabilityRules(
            positive=_rx(rd["positive"]),
            negative=_rx(rd["negative"]),
            class_weight=float(rd.get("class_weight", 25)),
            tag_scores={k: float(v) for k, v in rd.get("tag_scores", {}).items()},
            min_paragraph_chars=int(rd.get("min_paragraph_chars", 25)),
            sibling_threshold_ratio=float(rd.get("sibling_threshold_ratio", 0.2)),
            sibling_threshold_min=float(rd.get("sibling_threshold_min", 10)),
        ),
        source=p,
    )
