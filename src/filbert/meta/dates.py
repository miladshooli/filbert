"""تاریخ انتشار/ویرایش: ISO 8601 و RFC 2822، تاریخ شمسی (`۱۴۰۵/۰۸/۱۰`، `۱۰ آبان ۱۴۰۵`) و میلادی در متن.

خروجی همیشه ISO 8601 (`YYYY-MM-DD` یا با زمان و منطقه)؛ مقدار خام در `*_raw` نگه داشته می‌شود.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime

import jdatetime

from filbert.fa.normalize import normalize_digits

JALALI_MONTHS: dict[str, int] = {
    "فروردین": 1,
    "اردیبهشت": 2,
    "خرداد": 3,
    "تیر": 4,
    "مرداد": 5,
    "امرداد": 5,
    "شهریور": 6,
    "مهر": 7,
    "آبان": 8,
    "ابان": 8,
    "آذر": 9,
    "اذر": 9,
    "دی": 10,
    "بهمن": 11,
    "اسفند": 12,
}
GREGORIAN_MONTHS_FA: dict[str, int] = {
    "ژانویه": 1,
    "فوریه": 2,
    "مارس": 3,
    "آوریل": 4,
    "آپریل": 4,
    "مه": 5,
    "می": 5,
    "ژوئن": 6,
    "جولای": 7,
    "ژوئیه": 7,
    "اوت": 8,
    "آگوست": 8,
    "سپتامبر": 9,
    "اکتبر": 10,
    "نوامبر": 11,
    "دسامبر": 12,
}
GREGORIAN_MONTHS_EN: dict[str, int] = {
    m: i + 1
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
    )
}
GREGORIAN_MONTHS_EN.update({m[:3]: i for m, i in list(GREGORIAN_MONTHS_EN.items())})

_JALALI_NUMERIC_RE = re.compile(
    r"(?<!\d)(1[34]\d\d)[/\-.](0?[1-9]|1[0-2])[/\-.](0?[1-9]|[12]\d|3[01])(?!\d)"
)
_JALALI_TEXT_RE = re.compile(
    r"(?<!\d)(0?[1-9]|[12]\d|3[01])\s*("
    + "|".join(JALALI_MONTHS)
    + r")(?:\s*ماه)?\s*(1[34]\d\d)(?!\d)"
)
_GREG_TEXT_FA_RE = re.compile(
    r"(?<!\d)(0?[1-9]|[12]\d|3[01])\s*("
    + "|".join(GREGORIAN_MONTHS_FA)
    + r")\s*((?:19|20)\d\d)(?!\d)"
)
_GREG_TEXT_EN_RE = re.compile(
    r"(?<!\w)("
    + "|".join(sorted(GREGORIAN_MONTHS_EN, key=len, reverse=True))
    + r")\.?\s+(0?[1-9]|[12]\d|3[01]),?\s+((?:19|20)\d\d)(?!\d)",
    re.IGNORECASE,
)
_GREG_NUMERIC_RE = re.compile(
    r"(?<!\d)((?:19|20)\d\d)[/\-.](0?[1-9]|1[0-2])[/\-.](0?[1-9]|[12]\d|3[01])(?!\d)"
)
_TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?")
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)


@dataclass(slots=True)
class ParsedDate:
    iso: str
    raw: str
    calendar: str  # "gregorian" | "jalali"
    source: str


def _iso(d: date | datetime) -> str:
    if isinstance(d, datetime):
        return d.isoformat(timespec="seconds")
    return d.isoformat()


def parse_iso_or_rfc(raw: str) -> str | None:
    """ISO 8601 (با یا بی زمان/منطقه) یا RFC 2822 → ISO؛ وگرنه None."""
    s = normalize_digits(raw.strip(), "en")
    if not s:
        return None
    if _ISO_RE.match(s):
        try:
            if len(s) == 10:
                return date.fromisoformat(s).isoformat()
            return _iso(datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T")))
        except ValueError:
            pass
    try:
        return _iso(parsedate_to_datetime(s))
    except (TypeError, ValueError, IndexError):
        return None


def jalali_to_iso(year: int, month: int, day: int) -> str | None:
    try:
        return jdatetime.date(year, month, day).togregorian().isoformat()
    except ValueError:
        return None


def parse_text(text: str, *, source: str = "text") -> ParsedDate | None:
    """اولین تاریخ معتبر در متن (شمسی یا میلادی)؛ زمان `HH:MM` بلافاصله بعد از آن اگر بود اضافه می‌شود."""
    s = normalize_digits(text, "en")
    candidates: list[tuple[int, ParsedDate]] = []

    def add(m: re.Match[str], iso_date: str | None, cal: str) -> None:
        if iso_date is None:
            return
        raw = m.group(0)
        tail = s[m.end() : m.end() + 12]
        tm = _TIME_RE.search(tail)
        iso = iso_date
        if tm and tail[: tm.start()].strip(" -،,|") == "":
            iso = f"{iso_date}T{int(tm.group(1)):02d}:{tm.group(2)}:{tm.group(3) or '00'}"
            raw = raw + tail[: tm.end()]
        candidates.append(
            (m.start(), ParsedDate(iso=iso, raw=raw.strip(), calendar=cal, source=source))
        )

    for m in _JALALI_NUMERIC_RE.finditer(s):
        add(m, jalali_to_iso(int(m.group(1)), int(m.group(2)), int(m.group(3))), "jalali")
    for m in _JALALI_TEXT_RE.finditer(s):
        add(m, jalali_to_iso(int(m.group(3)), JALALI_MONTHS[m.group(2)], int(m.group(1))), "jalali")
    for m in _GREG_NUMERIC_RE.finditer(s):
        with contextlib.suppress(ValueError):
            add(m, date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat(), "gregorian")
    for m in _GREG_TEXT_FA_RE.finditer(s):
        with contextlib.suppress(ValueError):
            add(
                m,
                date(int(m.group(3)), GREGORIAN_MONTHS_FA[m.group(2)], int(m.group(1))).isoformat(),
                "gregorian",
            )
    for m in _GREG_TEXT_EN_RE.finditer(s):
        with contextlib.suppress(ValueError):
            add(
                m,
                date(
                    int(m.group(3)), GREGORIAN_MONTHS_EN[m.group(1).lower()], int(m.group(2))
                ).isoformat(),
                "gregorian",
            )
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]


def parse_any(raw: str | None, *, source: str) -> ParsedDate | None:
    """ISO/RFC اول، بعد جست‌وجوی متنی (شمسی/میلادی)."""
    if not raw:
        return None
    iso = parse_iso_or_rfc(raw)
    if iso:
        return ParsedDate(iso=iso, raw=raw.strip(), calendar="gregorian", source=source)
    return parse_text(raw, source=source)
