"""نرمال‌سازی متن فارسی — فقط روی `content.text` و `content.markdown`؛ هرگز روی متادیتا.

قواعد (بخش «ملاحظات فارسی» BLUEPRINT):
- حروف عربی → فارسی: ي→ی، ك→ک، ة→ه، ى→ی. ؤ/ئ دست نمی‌خورند.
- ارقام: عربی‌هندی → فارسی (پیش‌فرض)؛ با `digits="en"` همه → ASCII.
- اعراب فقط با `strip_diacritics=True` حذف می‌شود.
- ZWNJ (U+200C) **هرگز** حذف نمی‌شود، مگر تکراری، کنار فاصله/خط، یا ابتدا/انتهای متن.
- ZWSP/LRM/RLM/BOM/WJ/SHY حذف؛ NBSP → فاصله.
- فاصله‌های تکراری فشرده؛ بیش از یک خط خالی حذف؛ بعد از «،؛؟» فاصله و قبل از آن‌ها بدون فاصله.
تابع idempotent است: `normalize_text(normalize_text(x)) == normalize_text(x)`.
"""

from __future__ import annotations

import re

ZWNJ = "‌"

_CHAR_MAP = str.maketrans(
    {
        "ي": "ی",  # ي → ی
        "ى": "ی",  # ى → ی
        "ك": "ک",  # ك → ک
        "ة": "ه",  # ة → ه
        " ": " ",  # NBSP → فاصله
        "​": None,  # ZWSP
        "‎": None,  # LRM
        "‏": None,  # RLM
        "‪": None,
        "‫": None,
        "‬": None,
        "‭": None,
        "‮": None,  # bidi embeds
        "⁠": None,  # word joiner
        "­": None,  # soft hyphen
        "﻿": None,  # BOM
    }
)
_ARABIC_TO_FA_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹")
_ALL_TO_EN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIACRITICS_RE = re.compile(r"[ً-ْٰـ]")  # اعراب + کشیده
_SPACES_RE = re.compile(r"[ \t\f\v]+")
_ZWNJ_RUN_RE = re.compile(f"{ZWNJ}{{2,}}")
_ZWNJ_NEAR_WS_RE = re.compile(f"{ZWNJ}*(\\s){ZWNJ}*")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_FA_PUNCT = "،؛؟"
_SPACE_BEFORE_PUNCT_RE = re.compile(f" +([{_FA_PUNCT}])")
_NO_SPACE_AFTER_PUNCT_RE = re.compile(f"([{_FA_PUNCT}])(?=[^\\s{_FA_PUNCT}.!?»)\\]}}‌])")
_DIGIT_COMMA_DIGIT_RE = re.compile(r"(?<=[\d۰-۹])،(?=[\d۰-۹])")


def normalize_chars(text: str) -> str:
    """فقط یکسان‌سازی حروف و حذف کاراکترهای ناپیدا (بدون دست‌کاری فاصله)."""
    return text.translate(_CHAR_MAP)


def normalize_digits(text: str, digits: str = "fa") -> str:
    if digits == "en":
        return text.translate(_ALL_TO_EN_DIGITS)
    return text.translate(_ARABIC_TO_FA_DIGITS)


def strip_diacritics(text: str) -> str:
    return _DIACRITICS_RE.sub("", text)


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACES_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANK_LINES_RE.sub("\n\n", text).strip()


def normalize_zwnj(text: str) -> str:
    """ZWNJ تکراری → یکی؛ ZWNJ کنار فاصله/خط یا ابتدا/انتها → حذف. ZWNJ بین حروف دست نمی‌خورد."""
    text = _ZWNJ_RUN_RE.sub(ZWNJ, text)
    text = _ZWNJ_NEAR_WS_RE.sub(r"\1", text)
    return text.strip(ZWNJ)


def fix_punctuation_spacing(text: str) -> str:
    # «۱،۰۰۰» (جداکننده هزارگان با ویرگول فارسی) موقتاً محافظت می‌شود
    text = _DIGIT_COMMA_DIGIT_RE.sub("\x00", text)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _NO_SPACE_AFTER_PUNCT_RE.sub(r"\1 ", text)
    return text.replace("\x00", "،")


def normalize_text(text: str, *, digits: str = "fa", strip_diacritics_: bool = False) -> str:
    """نرمال‌سازی کامل؛ idempotent و حافظ ZWNJ معتبر."""
    if not text:
        return ""
    t = normalize_chars(text)
    t = normalize_digits(t, digits)
    if strip_diacritics_:
        t = strip_diacritics(t)
    t = normalize_whitespace(t)
    t = normalize_zwnj(t)
    t = fix_punctuation_spacing(t)
    t = normalize_whitespace(t)
    return normalize_zwnj(t)
