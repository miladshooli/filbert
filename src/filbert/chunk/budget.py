"""شمارنده اندازه چانک: کلمه (پیش‌فرض)، کاراکتر، یا tiktoken (اختیاری)."""

from __future__ import annotations

from collections.abc import Callable

from filbert.fa.tokenize import word_count

Counter = Callable[[str], int]


def get_counter(unit: str = "words", model: str = "o200k_base") -> Counter:
    if unit == "words":
        return word_count
    if unit == "chars":
        return lambda t: len(t)
    if unit == "tiktoken":
        try:
            import tiktoken
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("unit=tiktoken needs `pip install tiktoken`") from e
        enc = tiktoken.get_encoding(model)
        return lambda t: len(enc.encode(t))
    raise ValueError(f"unknown unit {unit!r}; use words|chars|tiktoken")
