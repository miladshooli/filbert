"""جداکننده جمله فارسی (ZWNJ-امن).

پایان‌دهنده سخت: «. ! ? ؟ …» و خط جدید. استثناها: اعشار، URL/ایمیل، اختصارهای نقطه‌دار، نقل‌قول/پرانتز بسته
پس از نقطه (به جمله قبلی می‌چسبد). «؛» و «:» فقط با `soft=True` مرز می‌شوند.
"""

from __future__ import annotations

import re

HARD_ENDERS = ".!?؟…"
SOFT_ENDERS = "؛:"
_CLOSERS = "»\"')\\]}”’"
_ABBREV = frozenset(
    {
        "ر.ک",
        "ق.م",
        "ه.ش",
        "ه.ق",
        "ه.ک",
        "ص",
        "صص",
        "ج",
        "ش",
        "م",
        "ق",
        "ع",
        "ره",
        "س",
        "e.g",
        "i.e",
        "etc",
        "vs",
        "dr",
        "mr",
        "mrs",
        "no",
    }
)
_URL_RE = re.compile(r"(?:https?://|www\.)\S+|\S+@\S+\.\S+", re.IGNORECASE)
_DOTTED_LETTERS_RE = re.compile(r"^(?:[\w؀-ۿ]\.){1,3}[\w؀-ۿ]?\.?$")
_DECIMAL_RE = re.compile(r"[\d۰-۹٠-٩][.٫,][\d۰-۹٠-٩]")


def _is_abbrev(prev: str) -> bool:
    tok = prev.rstrip(HARD_ENDERS + _CLOSERS).split()
    if not tok:
        return False
    last = tok[-1].strip("«(\"'[")
    low = last.lower().rstrip(".")
    return low in _ABBREV or bool(_DOTTED_LETTERS_RE.match(last))


def split_sentences(text: str, *, soft: bool = False) -> list[str]:
    """متن یک پاراگراف → جمله‌ها (strip شده، بدون خالی). offsetها لازم نیستند؛ متن چانک از همین‌ها ساخته می‌شود."""
    if not text:
        return []
    enders = HARD_ENDERS + (SOFT_ENDERS if soft else "")
    # URLها را موقتاً نگه می‌داریم تا نقطه‌هایشان مرز نشود
    urls: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        urls.append(m.group(0))
        return f"\x00{len(urls) - 1}\x00"

    s = _URL_RE.sub(_stash, text)
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(s)
    start = 0
    while i < n:
        ch = s[i]
        if ch == "\n":
            seg = s[start:i].strip()
            if seg:
                buf.append(seg)
                out.append(" ".join(buf))
                buf = []
            start = i + 1
            i += 1
            continue
        if ch in enders:
            j = i + 1
            while j < n and s[j] in enders:  # «...» یا «؟!»
                j += 1
            while j < n and s[j] in _CLOSERS:
                j += 1
            at_end = j >= n or s[j].isspace()
            if not at_end:
                i += 1
                continue
            seg = s[start:j].strip()
            prev_char = s[i - 1] if i > 0 else ""
            next_char = s[j + 1] if j + 1 < n else ""
            decimal = (
                ch in ".٫"
                and prev_char.isdigit()
                and next_char.isdigit()
                and not s[j : j + 1].isspace()
            )
            if ch == "." and _DECIMAL_RE.search(s[max(0, i - 1) : i + 2]) and not at_end:
                i += 1
                continue
            if ch == "." and _is_abbrev(seg):
                buf.append(seg)  # اختصار: به جمله بعدی می‌چسبد
                start = j
                i = j
                continue
            if seg and not decimal:
                buf.append(seg)
                out.append(" ".join(buf))
                buf = []
            start = j
            i = j
            continue
        i += 1
    tail = s[start:].strip()
    if tail:
        buf.append(tail)
    if buf:
        out.append(" ".join(buf))
    if urls:
        out = [re.sub(r"\x00(\d+)\x00", lambda m: urls[int(m.group(1))], o) for o in out]
    return [o for o in (x.strip() for x in out) if o]


def ends_at_boundary(text: str) -> bool:
    """آیا متن روی مرز جمله/بلوک تمام شده (برای سنجش کیفیت چانک)."""
    t = text.rstrip()
    if not t:
        return True
    t = t.rstrip(_CLOSERS)
    return t.endswith(tuple(HARD_ENDERS + SOFT_ENDERS)) or t.endswith(("|", "```"))
