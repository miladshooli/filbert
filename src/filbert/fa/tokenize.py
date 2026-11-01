"""شمارش کلمه برای فارسی: ZWNJ مرز کلمه نیست («می‌شود» یک کلمه)؛ عدد و کلمه انگلیسی هر کدام یک کلمه."""

from __future__ import annotations

import re

ZWNJ = "‌"
# عدد (با جداکننده اعشار/هزارگان) | کلمه (حروف/ارقام) که با ZWNJ به هم وصل شده‌اند
_TOKEN_RE = re.compile(rf"\d[\d.,٫٬]*\d|\w+(?:{ZWNJ}\w+)*", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def word_count(text: str) -> int:
    return len(_TOKEN_RE.findall(text))


def char_count(text: str) -> int:
    """تعداد کاراکتر بدون فاصله‌های ابتدا/انتها (ZWNJ شمرده می‌شود)."""
    return len(text.strip())


def reading_time_min(words: int, wpm: int = 200) -> int:
    if words <= 0:
        return 0
    return max(1, round(words / wpm))
