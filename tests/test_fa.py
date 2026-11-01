import re

from hypothesis import given, settings
from hypothesis import strategies as st

from filbert.fa.normalize import ZWNJ, normalize_text, normalize_zwnj
from filbert.fa.tokenize import reading_time_min, tokenize, word_count

FA_LETTERS = "ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیيكةآأإؤئ"
EXTRA = " \n\t ​‎‏﻿،؛؟.,!0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩abcXYZًّ"
ALPHABET = FA_LETTERS + ZWNJ + EXTRA
_VALID_ZWNJ_RE = re.compile(f"[{FA_LETTERS}]{ZWNJ}[{FA_LETTERS}]")


def test_char_mapping() -> None:
    assert normalize_text("كيف پول ة") == "کیف پول ه"
    assert normalize_text("ؤ ئ") == "ؤ ئ"  # بدون تغییر


def test_digits() -> None:
    assert normalize_text("٠١٢ ۳۴ 56") == "۰۱۲ ۳۴ 56"
    assert normalize_text("٠١٢ ۳۴ 56", digits="en") == "012 34 56"


def test_diacritics_optional() -> None:
    s = "مَدرَسه"
    assert normalize_text(s) == s
    assert normalize_text(s, strip_diacritics_=True) == "مدرسه"


def test_invisible_chars() -> None:
    assert normalize_text("الف​ب‎ج‏د﻿") == "الفبجد"
    assert normalize_text("الف ب") == "الف ب"


def test_zwnj_rules() -> None:
    assert normalize_text("می‌شود") == "می‌شود"  # حفظ
    assert normalize_text("می‌‌شود") == "می‌شود"  # تکراری
    assert normalize_text("می‌ شود") == "می شود"  # کنار فاصله
    assert normalize_text("‌می‌شود‌") == "می‌شود"  # ابتدا/انتها
    assert normalize_text("می شود") == "می شود"  # فاصله به ZWNJ تبدیل نمی‌شود


def test_whitespace_and_punct() -> None:
    assert normalize_text("الف   ب\t ج") == "الف ب ج"
    assert normalize_text("الف\n\n\n\nب") == "الف\n\nب"
    assert normalize_text("الف ،ب") == "الف، ب"
    assert normalize_text("الف؛ب؟ج") == "الف؛ ب؟ ج"
    assert normalize_text("۱،۰۰۰ تومان") == "۱،۰۰۰ تومان"
    assert normalize_text("سلام،»") == "سلام،»"


@settings(max_examples=500)
@given(st.text(alphabet=ALPHABET, max_size=80))
def test_idempotent(s: str) -> None:
    once = normalize_text(s)
    assert normalize_text(once) == once


@settings(max_examples=500)
@given(st.text(alphabet=ALPHABET, max_size=80))
def test_idempotent_en_digits_strip(s: str) -> None:
    once = normalize_text(s, digits="en", strip_diacritics_=True)
    assert normalize_text(once, digits="en", strip_diacritics_=True) == once


@settings(max_examples=500)
@given(st.text(alphabet=ALPHABET, max_size=80))
def test_valid_zwnj_never_dropped(s: str) -> None:
    """هر ZWNJ معتبر (بین دو حرف) در خروجی باقی می‌ماند."""
    before = len(_VALID_ZWNJ_RE.findall(s))
    after = len(_VALID_ZWNJ_RE.findall(normalize_text(s)))
    assert after >= before


@given(st.text(alphabet=FA_LETTERS + ZWNJ, min_size=1, max_size=40))
def test_zwnj_only_between_letters_unchanged(s: str) -> None:
    s = s.strip(ZWNJ)
    s = re.sub(f"{ZWNJ}+", ZWNJ, s)
    assert normalize_zwnj(s) == s


def test_word_count_zwnj_not_boundary() -> None:
    assert word_count("می‌شود") == 1
    assert word_count("می شود") == 2
    assert word_count("کتاب‌ها و دفترها") == 3
    assert tokenize("قیمت USDT امروز 3.5 درصد و ۱۲٬۰۰۰ تومان") == [
        "قیمت",
        "USDT",
        "امروز",
        "3.5",
        "درصد",
        "و",
        "۱۲٬۰۰۰",
        "تومان",
    ]
    assert word_count("") == 0
    assert word_count("، ؛ ...") == 0


def test_reading_time() -> None:
    assert reading_time_min(0) == 0
    assert reading_time_min(50) == 1
    assert reading_time_min(1240) == 6
