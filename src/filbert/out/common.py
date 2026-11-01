"""ابزار مشترک نویسنده‌ها."""

from __future__ import annotations

from filbert.models import PageRecord

RTL_LANGS: frozenset[str] = frozenset({"fa", "ar", "he", "ur", "ps", "ckb", "ug", "yi", "dv"})


def direction_for(lang: str | None) -> str:
    return "rtl" if (lang or "").lower() in RTL_LANGS else "ltr"


def page_lang(record: PageRecord, default: str = "fa") -> str:
    return record.seo.lang_detected or record.seo.lang_declared or default
