"""خروجی Excel از `pages.jsonl` (extras `[export]`، openpyxl): برگه‌های pages/issues/headings/links/images/chunks.

راست‌چین، عنوان‌ها bold و freeze شده، عرض ستون‌ها تنظیم‌شده؛ ZWNJ دست‌نخورده.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import orjson

from filbert.models import PageRecord
from filbert.out.issues import find_issues

_PAGE_COLUMNS = (
    ("url", lambda r: r.final_url or r.url),
    ("status", lambda r: r.http.status),
    ("title", lambda r: r.seo.title),
    ("title_length", lambda r: r.seo.title_length),
    ("h1", lambda r: r.seo.h1),
    ("description", lambda r: r.seo.description),
    ("description_length", lambda r: r.seo.description_length),
    ("description_px", lambda r: r.seo.description_px_est),
    ("canonical", lambda r: r.canonical),
    ("robots", lambda r: r.seo.robots.raw),
    ("lang_declared", lambda r: r.seo.lang_declared),
    ("lang_detected", lambda r: r.seo.lang_detected),
    ("author", lambda r: r.seo.author),
    ("published_at", lambda r: r.seo.published_at),
    ("modified_at", lambda r: r.seo.modified_at),
    ("json_ld_types", lambda r: ", ".join(r.seo.json_ld_types)),
    ("word_count", lambda r: r.content.word_count),
    ("reading_time_min", lambda r: r.content.reading_time_min),
    ("confidence", lambda r: r.content.confidence),
    ("low_confidence", lambda r: r.content.low_confidence),
    ("headings", lambda r: len(r.structure.headings)),
    ("links_internal", lambda r: r.structure.links_summary.internal),
    ("links_external", lambda r: r.structure.links_summary.external),
    ("links_nofollow", lambda r: r.structure.links_summary.nofollow),
    ("images", lambda r: r.structure.images_summary.total),
    ("images_missing_alt", lambda r: r.structure.images_summary.missing_alt),
    ("chunks", lambda r: len(r.content.chunks)),
    ("rendered", lambda r: r.http.rendered),
    ("content_hash", lambda r: r.content_hash),
    ("fetched_at", lambda r: r.fetched_at.isoformat(timespec="seconds") if r.fetched_at else None),
)


def read_records(path: Path) -> Iterable[PageRecord]:
    p = Path(path)
    if p.is_dir():
        p = p / "pages.jsonl"
    with p.open("rb") as fh:
        for line in fh:
            if line.strip():
                yield PageRecord.model_validate(orjson.loads(line))


def export_xlsx(
    source: Path, out: Path, *, include_chunks: bool = True, max_links: int = 50_000
) -> dict[str, int]:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
        from openpyxl.utils import get_column_letter
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Excel export needs `uv sync --extra export` (openpyxl)") from e

    wb = Workbook()
    sheets: dict[str, list[list[object]]] = {
        "pages": [[c for c, _ in _PAGE_COLUMNS]],
        "issues": [["url", "severity", "code", "detail"]],
        "headings": [["url", "level", "text", "in_main"]],
        "links": [["url", "target", "anchor", "internal", "nofollow", "in_main"]],
        "images": [["url", "src", "alt", "in_main"]],
    }
    if include_chunks:
        sheets["chunks"] = [["url", "index", "heading_path", "word_count", "text"]]
    counts = {k: 0 for k in sheets}
    for rec in read_records(source):
        url = rec.final_url or rec.url
        sheets["pages"].append([fn(rec) for _, fn in _PAGE_COLUMNS])
        for iss in find_issues(rec):
            sheets["issues"].append([url, iss.severity, iss.code, iss.detail])
        for h in rec.structure.headings:
            sheets["headings"].append([url, h.level, h.text, h.in_main])
        for ln in rec.structure.links:
            if len(sheets["links"]) > max_links:
                break
            sheets["links"].append([url, ln.url, ln.anchor, ln.internal, ln.nofollow, ln.in_main])
        for im in rec.structure.images:
            sheets["images"].append([url, im.src, im.alt, im.in_main])
        if include_chunks:
            for ch in rec.content.chunks:
                sheets["chunks"].append(
                    [url, ch.index, " › ".join(ch.heading_path), ch.word_count, ch.text]
                )
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet()
        first = False
        ws.title = name
        ws.sheet_view.rightToLeft = True
        for row in rows:
            ws.append([_cell(v) for v in row])
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for i, header in enumerate(rows[0], start=1):
            width = (
                60
                if header in ("text", "description", "detail")
                else 40
                if header in ("url", "target", "src", "title", "canonical")
                else 16
            )
            ws.column_dimensions[get_column_letter(i)].width = width
        counts[name] = len(rows) - 1
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return counts


def _cell(v: object) -> object:
    if isinstance(v, str):
        # کاراکترهای کنترلی غیرمجاز در XML را حذف کن؛ ZWNJ (U+200C) مجاز است و می‌ماند
        v = "".join(ch for ch in v if ch >= " " or ch in "\t\n")
        return v[:32000]
    return v
