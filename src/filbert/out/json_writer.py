"""خروجی JSON با orjson؛ UTF-8 بدون escape یونیکد (پیش‌فرض orjson)."""

from __future__ import annotations

import orjson

from filbert.models import PageRecord


def dumps(record: PageRecord, *, indent: bool = True) -> bytes:
    opt = orjson.OPT_INDENT_2 if indent else 0
    return orjson.dumps(record.model_dump(mode="json"), option=opt)


def dumps_line(record: PageRecord) -> bytes:
    """یک خط JSONL (بدون newline انتهایی)."""
    return orjson.dumps(record.model_dump(mode="json"))
