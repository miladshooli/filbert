"""Layout دیسک برای یک اجرا:

output/<run-id>/{pages.jsonl, errors.jsonl, run.json, json/<slug>.json, html/<slug>.html, md/<slug>.md}

`<slug>` = host + مسیر پاک‌شده (حداکثر ۱۲۰ کاراکتر) + ۸ کاراکتر اول hash؛ ویندوزسازگار.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

import orjson

from filbert.models import PageRecord, RunStats
from filbert.out import html_writer, json_writer, md_writer

FORMATS: tuple[str, ...] = ("json", "html", "md")
_BAD_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f%#&=+\s]+')
_DASHES_RE = re.compile(r"-{2,}")
_WIN_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def make_run_id(now: datetime | None = None) -> str:
    """`YYYYMMDD-HHMMSS-xxxx`؛ پسوند تصادفی تا دو اجرا در یک ثانیه یک پوشه نشوند."""
    return (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def slugify_url(url: str, max_len: int = 120) -> str:
    parts = urlsplit(url)
    raw = f"{parts.hostname or 'local'}{unquote(parts.path)}"
    if parts.query:
        raw += "-" + unquote(parts.query)
    slug = _BAD_CHARS_RE.sub("-", raw)
    slug = _DASHES_RE.sub("-", slug).strip("-. ")
    slug = slug[:max_len].rstrip("-. ") or "page"
    if slug.lower() in _WIN_RESERVED:
        slug = f"_{slug}"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


class Store:
    def __init__(
        self, out_dir: Path, run_id: str | None = None, formats: tuple[str, ...] = FORMATS
    ) -> None:
        unknown = set(formats) - set(FORMATS)
        if unknown:
            raise ValueError(f"unknown formats: {sorted(unknown)}")
        self.run_id = run_id or make_run_id()
        self.root = Path(out_dir) / self.run_id
        self.formats = tuple(formats)
        self.root.mkdir(parents=True, exist_ok=True)
        for f in self.formats:
            (self.root / f).mkdir(exist_ok=True)
        self._pages = open(self.root / "pages.jsonl", "ab")  # noqa: SIM115
        self._errors = open(self.root / "errors.jsonl", "ab")  # noqa: SIM115
        self._chunks = open(self.root / "chunks.jsonl", "ab")  # noqa: SIM115

    def write(self, record: PageRecord) -> dict[str, Path]:
        slug = slugify_url(record.final_url or record.url)
        paths: dict[str, Path] = {}
        if "json" in self.formats:
            p = self.root / "json" / f"{slug}.json"
            p.write_bytes(json_writer.dumps(record))
            paths["json"] = p
        if "html" in self.formats:
            p = self.root / "html" / f"{slug}.html"
            p.write_text(html_writer.render(record), encoding="utf-8")
            paths["html"] = p
        if "md" in self.formats:
            p = self.root / "md" / f"{slug}.md"
            p.write_text(md_writer.render(record), encoding="utf-8")
            paths["md"] = p
        self._pages.write(json_writer.dumps_line(record) + b"\n")
        self._pages.flush()
        if record.content.chunks:
            base = {
                "url": record.final_url or record.url,
                "title": record.seo.title,
                "lang": record.seo.lang_detected or record.seo.lang_declared,
            }
            for ch in record.content.chunks:
                self._chunks.write(orjson.dumps({**base, **ch.model_dump(mode="json")}) + b"\n")
            self._chunks.flush()
        return paths

    def write_error(self, url: str, reason: str, status: int | None = None) -> None:
        line = {"url": url, "reason": reason, "status": status, "at": datetime.now(UTC).isoformat()}
        self._errors.write(orjson.dumps(line) + b"\n")
        self._errors.flush()

    def finish(self, stats: RunStats) -> Path:
        stats.finished_at = stats.finished_at or datetime.now(UTC)
        p = self.root / "run.json"
        p.write_bytes(orjson.dumps(stats.model_dump(mode="json"), option=orjson.OPT_INDENT_2))
        self.close()
        return p

    def close(self) -> None:
        for fh in (self._pages, self._errors, self._chunks):
            if not fh.closed:
                fh.close()
