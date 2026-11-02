"""چانکر ساختاری: واحد پایه بلوک است؛ مرز سخت = هدینگ تا سطح مؤثر N؛ بودجه کلمه؛ هم‌پوشانی جمله‌ای.

ورودی: بلوک‌های برنده به ترتیب سند (`Block`). خروجی: `list[Chunk]`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from filbert.chunk.budget import Counter, get_counter
from filbert.chunk.sentence import split_sentences
from filbert.fa.normalize import normalize_text
from filbert.models import Block, Chunk

HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
ATOMIC = frozenset({"table", "pre", "blockquote", "figure"})
LISTS = frozenset({"ul", "ol"})
MAX_HEADING_CHARS = 120
TAIL_MERGE_RATIO = 0.3


@dataclass(slots=True)
class ChunkOptions:
    max_units: int = 250  # هدف
    hard_max: int = 400  # سقف سخت (فقط بلوک اتمی/جمله تکی می‌تواند بگذرد)
    overlap_sentences: int = 1
    heading_level: int = 3  # مرز سخت تا این سطحِ مؤثر
    unit: str = "words"
    context_prefix: bool = True  # تیتر › مسیر هدینگ در embed_text
    min_section_ratio: float = (
        0.15  # بخشِ یک‌چانکی کوچک‌تر از این نسبت از بودجه، با چانک قبلی ادغام می‌شود
    )
    promote_bold_headings: bool = False
    digits: str = "fa"


@dataclass(slots=True)
class _Unit:
    text: str  # خام
    types: list[str]
    xpath_start: str
    xpath_end: str
    atomic: bool = False
    sentences: list[str] | None = None  # برای برش پاراگراف


@dataclass(slots=True)
class _Section:
    path: list[str]
    units: list[_Unit] = field(default_factory=list)


def _effective_levels(blocks: list[Block]) -> dict[int, int]:
    """نگاشت سطح تگ → سطح مؤثر (۱..k) بر اساس سطوح موجود؛ H1 اول تیتر است."""
    levels = sorted({int(b.type[1]) for b in blocks if b.type in HEADINGS and _is_real_heading(b)})
    return {lvl: i + 1 for i, lvl in enumerate(levels)}


def _is_real_heading(b: Block) -> bool:
    t = b.text.strip()
    return 0 < len(t) <= MAX_HEADING_CHARS and "\n" not in t


def build_sections(blocks: list[Block], opts: ChunkOptions) -> tuple[str | None, list[_Section]]:
    """بلوک‌ها → بخش‌ها (مسیر هدینگ + واحدها). هدینگ بخش خالی نادیده گرفته می‌شود."""
    eff = _effective_levels(blocks)
    title: str | None = None
    stack: list[tuple[int, str]] = []  # (سطح مؤثر، متن)
    sections: list[_Section] = [_Section(path=[])]
    pending_heading: tuple[int, str] | None = None
    seen_h1 = False

    def path_now() -> list[str]:
        return [t for _, t in stack]

    for b in blocks:
        if b.type in HEADINGS and _is_real_heading(b):
            raw_level = int(b.type[1])
            if raw_level == 1 and not seen_h1:
                seen_h1 = True
                title = b.text.strip()
                continue
            level = eff.get(raw_level, raw_level)
            if raw_level == 1:
                level = 1
            level = min(level, opts.heading_level + 1)  # عمیق‌تر از مرز سخت، همه یک سطح
            # هدینگ قبلیِ بدون محتوا (بخش خالی) جایگزین می‌شود
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, b.text.strip()))
            if pending_heading is not None and not sections[-1].units:
                sections[-1].path = path_now()
            else:
                sections.append(_Section(path=path_now()))
            pending_heading = (level, b.text.strip())
            continue
        pending_heading = None
        sec = sections[-1]
        text = b.text.strip()
        if not text:
            continue
        unit = _Unit(
            text=text,
            types=[b.type],
            xpath_start=b.xpath,
            xpath_end=b.xpath,
            atomic=b.type in ATOMIC,
        )
        if (
            b.type in LISTS
            and sec.units
            and not sec.units[-1].atomic
            and sec.units[-1].text.rstrip().endswith((":", "："))
        ):
            intro = sec.units[-1]  # فهرست با جمله معرفش
            intro.text = intro.text + "\n" + text
            intro.types.append(b.type)
            intro.xpath_end = b.xpath
            intro.atomic = True
            continue
        if b.type in LISTS:
            unit.atomic = True
        sec.units.append(unit)
    sections = [s for s in sections if s.units]
    return title, sections


def _split_long_paragraph(unit: _Unit, count: Counter, opts: ChunkOptions) -> list[_Unit]:
    sents = split_sentences(unit.text) or [unit.text]
    if len(sents) == 1:
        sents = split_sentences(unit.text, soft=True) or sents
    out: list[_Unit] = []
    buf: list[str] = []
    n = 0
    for s in sents:
        c = count(s)
        if buf and n + c > opts.max_units:
            out.append(
                _Unit(
                    " ".join(buf),
                    list(unit.types),
                    unit.xpath_start,
                    unit.xpath_end,
                    sentences=list(buf),
                )
            )
            buf, n = [], 0
        buf.append(s)
        n += c
    if buf:
        out.append(
            _Unit(
                " ".join(buf),
                list(unit.types),
                unit.xpath_start,
                unit.xpath_end,
                sentences=list(buf),
            )
        )
    return out


def _split_table(unit: _Unit, count: Counter, opts: ChunkOptions) -> list[_Unit]:
    rows = [r for r in unit.text.split("\n\n") if r.strip()] or [unit.text]
    if len(rows) < 3:
        return [unit]
    header = rows[0]
    out: list[_Unit] = []
    buf: list[str] = [header]
    n = count(header)
    for r in rows[1:]:
        c = count(r)
        if len(buf) > 1 and n + c > opts.hard_max:
            out.append(
                _Unit(
                    "\n\n".join(buf),
                    list(unit.types),
                    unit.xpath_start,
                    unit.xpath_end,
                    atomic=True,
                )
            )
            buf, n = [header], count(header)
        buf.append(r)
        n += c
    if len(buf) > 1:
        out.append(
            _Unit("\n\n".join(buf), list(unit.types), unit.xpath_start, unit.xpath_end, atomic=True)
        )
    return out


def _split_lines(unit: _Unit, count: Counter, opts: ChunkOptions, sep: str) -> list[_Unit]:
    """فهرست بلند بر اساس آیتم (خط) و کد بلند بر اساس خط؛ هر تکه ≤ سقف سخت."""
    lines = [ln for ln in unit.text.split(sep) if ln.strip()]
    if len(lines) < 2:
        return [unit]
    out: list[_Unit] = []
    buf: list[str] = []
    n = 0
    for ln in lines:
        c = count(ln)
        if buf and n + c > opts.hard_max:
            out.append(
                _Unit(
                    sep.join(buf), list(unit.types), unit.xpath_start, unit.xpath_end, atomic=True
                )
            )
            buf, n = [], 0
        buf.append(ln)
        n += c
    if buf:
        out.append(
            _Unit(sep.join(buf), list(unit.types), unit.xpath_start, unit.xpath_end, atomic=True)
        )
    return out


def _expand_units(units: list[_Unit], count: Counter, opts: ChunkOptions) -> list[_Unit]:
    out: list[_Unit] = []
    for u in units:
        c = count(u.text)
        if c <= opts.max_units:
            out.append(u)
        elif "table" in u.types:
            out.extend(_split_table(u, count, opts))
        elif c <= opts.hard_max and u.atomic:
            out.append(u)  # اتمیِ کمی بزرگ‌تر از هدف: دست نمی‌خورد
        elif "pre" in u.types or "ul" in u.types or "ol" in u.types:
            out.extend(_split_lines(u, count, opts, "\n"))  # کد: خط؛ فهرست: آیتم
        elif u.atomic:
            u2 = _Unit(u.text, u.types, u.xpath_start, u.xpath_end)  # نقل‌قول/figure بلند: روی جمله
            out.extend(_split_long_paragraph(u2, count, opts))
        else:
            out.extend(_split_long_paragraph(u, count, opts))
    return out


def _pack(units: list[_Unit], count: Counter, opts: ChunkOptions) -> list[list[_Unit]]:
    groups: list[list[_Unit]] = []
    cur: list[_Unit] = []
    n = 0
    for u in units:
        c = count(u.text)
        if cur and n + c > opts.max_units:
            groups.append(cur)
            cur, n = [], 0
        cur.append(u)
        n += c
    if cur:
        groups.append(cur)
    # ادغام دنباله کوتاه
    if len(groups) >= 2:
        last_n = sum(count(u.text) for u in groups[-1])
        prev_n = sum(count(u.text) for u in groups[-2])
        if last_n < TAIL_MERGE_RATIO * opts.max_units and last_n + prev_n <= opts.hard_max:
            groups[-2].extend(groups.pop())
    return groups


def _last_sentences(group: list[_Unit], k: int) -> list[str]:
    if k <= 0:
        return []
    for u in reversed(group):
        if u.atomic:
            return []
        sents = u.sentences or split_sentences(u.text)
        if sents:
            return sents[-k:]
    return []


def chunk_blocks(
    blocks: list[Block],
    *,
    opts: ChunkOptions | None = None,
    title: str | None = None,
    counter: Counter | None = None,
) -> list[Chunk]:
    opts = opts or ChunkOptions()
    count = counter or get_counter(opts.unit)
    page_title, sections = build_sections(blocks, opts)
    page_title = title or page_title
    chunks: list[Chunk] = []
    total_units = sum(count(u.text) for s in sections for u in s.units) or 1
    pos = 0
    for sec in sections:
        units = _expand_units(sec.units, count, opts)
        groups = _pack(units, count, opts)
        prev: list[_Unit] | None = None
        for gi, group in enumerate(groups):
            overlap = _last_sentences(prev, opts.overlap_sentences) if prev is not None else []
            body_raw = "\n\n".join(u.text for u in group)
            heading_line = sec.path[-1] if (gi == 0 and sec.path) else None
            text_raw = (heading_line + "\n\n" + body_raw) if heading_line else body_raw
            if overlap:
                text_raw = " ".join(overlap) + "\n\n" + text_raw
            text = normalize_text(text_raw, digits=opts.digits)
            ctx_parts = [p for p in [page_title, *sec.path] if p]
            embed = (
                (" › ".join(ctx_parts) + "\n\n" + text)
                if (opts.context_prefix and ctx_parts)
                else text
            )
            wc = count(body_raw)
            idx = len(chunks)
            chunks.append(
                Chunk(
                    id=f"{idx:03d}-{hashlib.blake2b(text.encode(), digest_size=4).hexdigest()}",
                    index=idx,
                    heading_path=list(sec.path),
                    text=text,
                    text_raw=text_raw,
                    embed_text=embed,
                    word_count=wc,
                    sentence_count=sum(len(u.sentences or split_sentences(u.text)) for u in group),
                    block_types=sorted({t for u in group for t in u.types}),
                    xpath_start=group[0].xpath_start,
                    xpath_end=group[-1].xpath_end,
                    position=round(pos / total_units, 3),
                    overlap_words=count(" ".join(overlap)) if overlap else 0,
                )
            )
            pos += wc
            prev = group
    return _merge_tiny_sections(chunks, count, opts)


def _merge_tiny_sections(chunks: list[Chunk], count: Counter, opts: ChunkOptions) -> list[Chunk]:
    """بخشِ یک‌چانکیِ خیلی کوچک (< ۳۰٪ بودجه؛ مثل «برند / مدل» در صفحه محصول) با چانک قبلی ادغام می‌شود
    اگر از سقف سخت نگذرد؛ مسیر هدینگ چانک قبلی می‌ماند و هدینگ بخش کوچک داخل متن است."""
    if len(chunks) < 2:
        return chunks
    threshold = opts.min_section_ratio * opts.max_units
    out: list[Chunk] = [chunks[0]]
    for ch in chunks[1:]:
        prev = out[-1]
        same_section_next = (
            False  # این چانک تنها چانک بخش خودش است؟ (ایندکس بعدی مسیر متفاوت دارد یا آخر است)
        )
        idx = ch.index
        nxt = chunks[idx + 1] if idx + 1 < len(chunks) else None
        same_section_next = nxt is not None and nxt.heading_path == ch.heading_path
        tiny = (
            ch.word_count < threshold
            and not same_section_next
            and ch.heading_path != prev.heading_path
        )
        if (
            tiny
            and prev.word_count + ch.word_count <= opts.hard_max
            and "table" not in prev.block_types
        ):
            merged_raw = prev.text_raw.rstrip() + "\n\n" + ch.text_raw
            merged_text = prev.text.rstrip() + "\n\n" + ch.text
            ctx = (
                prev.embed_text[: len(prev.embed_text) - len(prev.text)]
                if prev.embed_text.endswith(prev.text)
                else ""
            )
            out[-1] = prev.model_copy(
                update={
                    "text": merged_text,
                    "text_raw": merged_raw,
                    "embed_text": ctx + merged_text,
                    "word_count": prev.word_count + ch.word_count,
                    "sentence_count": prev.sentence_count + ch.sentence_count,
                    "block_types": sorted(set(prev.block_types) | set(ch.block_types)),
                    "xpath_end": ch.xpath_end,
                }
            )
            continue
        out.append(ch)
    for i, ch in enumerate(out):
        if ch.index != i:
            out[i] = ch.model_copy(update={"index": i, "id": f"{i:03d}-{ch.id.split('-', 1)[1]}"})
    return out


def chunk_sentences(
    blocks: list[Block], *, opts: ChunkOptions | None = None, title: str | None = None
) -> list[Chunk]:
    """حالت `sentences`: پنجره لغزان جمله‌ای بدون توجه به هدینگ (برای مقایسه)."""
    opts = opts or ChunkOptions()
    flat = [
        Block(type="p", text=b.text, html=b.html, xpath=b.xpath, votes=b.votes)
        for b in blocks
        if b.type not in HEADINGS
    ]
    return chunk_blocks(
        flat, opts=ChunkOptions(**{**opts.__dict__, "heading_level": 0}), title=title
    )
