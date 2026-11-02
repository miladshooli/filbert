"""تشخیص زبان بدون مدل: نسبت کاراکترهای عربی‌نویس/لاتین و حروف اختصاصی فارسی در برابر عربی.

نتیجه `fa` / `ar` / `en` / `mixed` / `other` به‌همراه درصدها. `lingua` (extras `[lang]`) اگر نصب باشد فقط برای
موارد مبهم (نسبت ۳۵–۶۵٪ یا فارسی/عربی نزدیک) روی ۵۰۰ کاراکتر اول استفاده می‌شود.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ARABIC_SCRIPT_RE = re.compile(r"[ء-يٮ-ۓەۺ-ۼۿݐ-ݿﭐ-﷿ﹰ-ﻼ]")
_LATIN_RE = re.compile(r"[A-Za-zÀ-ɏ]")
_FA_SPECIFIC_RE = re.compile(r"[پچژگکییکگچژپ]")
_AR_SPECIFIC_RE = re.compile(r"[ةيكءىًٌٍ]")  # ة ي ك ء ى تنوین
_FA_WORDS = frozenset(
    {
        "است",
        "که",
        "های",
        "می",
        "این",
        "را",
        "با",
        "از",
        "در",
        "به",
        "و",
        "برای",
        "شود",
        "کرد",
        "شده",
    }
)
_AR_WORDS = frozenset(
    {"في", "من", "على", "إلى", "التي", "الذي", "هذا", "هذه", "عن", "كان", "أن", "مع", "لم", "لا"}
)
_WORD_RE = re.compile(r"\w+", re.UNICODE)

MIXED_LOW, MIXED_HIGH = 0.2, 0.8


@dataclass(slots=True)
class LangResult:
    lang: str
    scores: dict[str, float] = field(default_factory=dict)  # نسبت‌ها در بازه ۰..۱
    method: str = "heuristic"


def detect(text: str | None, *, sample: int = 4000) -> LangResult:
    if not text:
        return LangResult("other")
    s = text[:sample]
    arabic = len(_ARABIC_SCRIPT_RE.findall(s))
    latin = len(_LATIN_RE.findall(s))
    letters = arabic + latin
    if letters < 20:
        return LangResult("other", {"arabic_script": 0.0, "latin": 0.0})
    r_ar = arabic / letters
    fa_sp = len(_FA_SPECIFIC_RE.findall(s))
    ar_sp = len(_AR_SPECIFIC_RE.findall(s))
    words = {w for w in _WORD_RE.findall(s)}
    fa_words = len(words & _FA_WORDS)
    ar_words = len(words & _AR_WORDS)
    fa_score = fa_sp + 3 * fa_words
    ar_score = ar_sp + 3 * ar_words
    sub = "fa" if fa_score >= ar_score else "ar"
    scores = {
        "arabic_script": round(r_ar, 3),
        "latin": round(1 - r_ar, 3),
        "fa_vs_ar": round(fa_score / (fa_score + ar_score), 3) if (fa_score + ar_score) else 0.5,
    }
    if r_ar >= MIXED_HIGH:
        lang = sub
    elif r_ar <= MIXED_LOW:
        lang = "en"
    else:
        lang = "mixed"
        scores["dominant"] = sub if r_ar >= 0.5 else "en"  # type: ignore[assignment]
    ambiguous = 0.35 <= r_ar <= 0.65 or (lang in ("fa", "ar") and abs(fa_score - ar_score) <= 2)
    if ambiguous:
        hint = _lingua(s[:500])
        if hint is not None:
            return LangResult(hint if hint != lang else lang, scores, method="lingua")
    return LangResult(lang, scores)


_LINGUA = None


def _lingua(sample: str) -> str | None:
    global _LINGUA
    if _LINGUA is False:
        return None
    if _LINGUA is None:
        try:
            from lingua import Language, LanguageDetectorBuilder

            _LINGUA = LanguageDetectorBuilder.from_languages(
                Language.PERSIAN, Language.ARABIC, Language.ENGLISH
            ).build()
        except Exception:  # noqa: BLE001 — اختیاری
            _LINGUA = False
            return None
    try:
        lang = _LINGUA.detect_language_of(sample)
    except Exception:  # noqa: BLE001
        return None
    if lang is None:
        return None
    return {"PERSIAN": "fa", "ARABIC": "ar", "ENGLISH": "en"}.get(lang.name)
