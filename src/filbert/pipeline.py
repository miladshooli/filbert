"""اتصال لایه‌ها: fetch → parse (یک بار) → meta → preclean → readability → نرمال‌سازی → PageRecord.

`extract_html` خالص و همزمان است (بدون شبکه)؛ `fetch_and_extract` async است و خروجی را روی دیسک می‌نویسد.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import statistics
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from filbert import __version__
from filbert.config import Settings
from filbert.extract import ensemble
from filbert.extract.cleanhtml import build_article
from filbert.extract.domtext import node_text, parse
from filbert.extract.preclean import preclean
from filbert.extract.rules import load_rules
from filbert.fa.normalize import normalize_text
from filbert.fa.tokenize import char_count, reading_time_min, word_count
from filbert.fetch.cache import Cache
from filbert.fetch.client import Fetcher, FetchError, FetchResult, decode_body, detect_encoding
from filbert.fetch.urlnorm import normalize_url
from filbert.meta import structure
from filbert.meta.enrich import enrich_head, finish
from filbert.meta.head import extract_head
from filbert.models import Content, HttpInfo, PageRecord, RunStats
from filbert.out.common import direction_for
from filbert.out.md_writer import render_body
from filbert.out.store import FORMATS, Store

log = logging.getLogger(__name__)
ProgressCallback = Callable[[PageRecord | None, str, str | None], None]


def content_hash(text: str) -> str:
    """اثرانگشت متن نرمال‌شده (blake2b-64؛ معادل سبک xxhash64 بدون وابستگی اضافه)."""
    return hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()


def extract_html(
    html: str,
    url: str,
    *,
    settings: Settings | None = None,
    final_url: str | None = None,
    http: HttpInfo | None = None,
    response_headers: Mapping[str, str] | None = None,
    fetched_at: datetime | None = None,
    raw_html_ref: str | None = None,
) -> PageRecord:
    """HTML → PageRecord بدون شبکه. تنها یک پارس selectolax."""
    settings = settings or Settings()
    rules = load_rules(settings.boilerplate_path)
    norm_url = normalize_url(url)
    final = normalize_url(final_url) if final_url else norm_url

    tree = parse(html)
    seo = extract_head(tree, final, response_headers)  # پیش از preclean: همان چیزی که گوگل می‌بیند
    seo, date_cands = enrich_head(seo, tree, final)
    structure_draft = structure.collect(tree, final)
    preclean(tree, rules.preclean)
    res = ensemble.extract(
        tree, rules, base_url=final, min_text_chars=settings.min_text_chars, recall=settings.recall
    )

    text_raw = res.text
    text = normalize_text(
        text_raw, digits=settings.digits, strip_diacritics_=settings.strip_diacritics
    )
    fallback_text = (
        None if len(text_raw) >= 200 or tree.body is None else node_text(tree.body)[:4000]
    )
    seo = finish(seo, date_cands, text_raw, fallback_text)
    lang = (
        seo.lang_declared
        or (seo.lang_detected if seo.lang_detected in ("fa", "ar", "en") else None)
        or settings.default_lang
    )
    words = word_count(text)
    chars = char_count(text)

    rec = PageRecord(
        url=norm_url,
        final_url=final,
        canonical=seo.canonical or final,
        fetched_at=fetched_at,
        http=http or HttpInfo(),
        seo=seo,
        content=Content(
            text=text,
            text_raw=text_raw,
            html=build_article(
                (b.html for b in res.blocks), lang=lang, direction=direction_for(lang)
            ),
            blocks=res.blocks,
            word_count=words,
            char_count=chars,
            reading_time_min=reading_time_min(words),
            confidence=res.confidence,
            low_confidence=res.low_confidence or chars < settings.min_text_chars,
            extractors=res.extractors,
        ),
        structure=structure.finalize(structure_draft, [b.node for b in res.raw_blocks]),
        content_hash=content_hash(text),
        raw_html_ref=raw_html_ref,
    )
    rec.content.markdown = render_body(rec)
    return rec


def extract_file(
    path: Path, url: str | None = None, settings: Settings | None = None
) -> PageRecord:
    """فایل HTML محلی → PageRecord. encoding با همان منطق لایه دریافت تشخیص داده می‌شود."""
    path = Path(path)
    body = path.read_bytes()
    enc = detect_encoding(body, None)
    html = decode_body(body, enc)
    page_url = url or path.resolve().as_uri()
    rec = extract_html(html, page_url, settings=settings, fetched_at=datetime.now(UTC))
    rec.http = HttpInfo(status=None, content_length=len(body), detected_encoding=enc)
    return rec


def record_from_fetch(fr: FetchResult, settings: Settings, cache: Cache | None) -> PageRecord:
    http = HttpInfo(
        status=fr.status,
        content_type=fr.headers.get("content-type"),
        content_length=len(fr.body),
        response_ms=fr.response_ms,
        redirects=fr.redirects,
        rendered=False,
        last_modified=fr.headers.get("last-modified"),
        etag=fr.headers.get("etag"),
        detected_encoding=fr.encoding,
        from_cache=fr.from_cache,
    )
    ref = cache.raw_ref(fr.raw_key) if (cache is not None and fr.raw_key) else None
    return extract_html(
        fr.text,
        fr.url,
        settings=settings,
        final_url=fr.final_url,
        http=http,
        response_headers=fr.headers,
        fetched_at=fr.fetched_at,
        raw_html_ref=ref,
    )


def is_url(s: str) -> bool:
    return s.lower().startswith(("http://", "https://"))


async def fetch_and_extract(
    inputs: list[str],
    *,
    settings: Settings | None = None,
    out_dir: Path | None = None,
    formats: tuple[str, ...] = FORMATS,
    force: bool = False,
    on_result: ProgressCallback | None = None,
) -> tuple[RunStats, list[PageRecord]]:
    """URLها/فایل‌ها را می‌گیرد، استخراج می‌کند و (اگر `out_dir` داده شود) روی دیسک می‌نویسد."""
    settings = settings or Settings()
    started = datetime.now(UTC)
    store = Store(out_dir, formats=formats) if out_dir is not None else None
    stats = RunStats(
        run_id=store.run_id if store else "-",
        tool_version=__version__,
        started_at=started,
        settings={"formats": list(formats), "force": force, "cache_dir": str(settings.cache_dir)},
        n=len(inputs),
    )
    records: list[PageRecord] = []
    durations: list[float] = []
    cache = Cache(settings.cache_dir)

    def handle(rec: PageRecord | None, source: str, error: str | None) -> None:
        if rec is not None:
            records.append(rec)
            stats.ok += 1
            if store is not None:
                store.write(rec)
        else:
            stats.failed += 1
            if store is not None:
                store.write_error(source, error or "unknown")
        if on_result is not None:
            on_result(rec, source, error)

    try:
        for src in [s for s in inputs if not is_url(s)]:
            t0 = time.perf_counter()
            try:
                rec = extract_file(Path(src), settings=settings)
            except (OSError, ValueError) as e:
                log.warning("file %s failed: %s", src, e)
                handle(None, src, f"{type(e).__name__}: {e}")
                continue
            durations.append((time.perf_counter() - t0) * 1000)
            handle(rec, src, None)

        urls = [s for s in inputs if is_url(s)]
        if urls:
            async with Fetcher(settings, cache) as fetcher:

                async def one(u: str) -> None:
                    t0 = time.perf_counter()
                    try:
                        fr = await fetcher.fetch(u, force=force)
                    except FetchError as e:
                        handle(None, u, e.reason)
                        return
                    try:
                        rec = record_from_fetch(fr, settings, cache)
                    except Exception as e:  # noqa: BLE001 — خطای استخراج نباید اجرا را بخواباند
                        log.exception("extract %s failed", u)
                        handle(None, u, f"extract: {type(e).__name__}: {e}")
                        return
                    durations.append((time.perf_counter() - t0) * 1000)
                    handle(rec, u, None)

                await asyncio.gather(*(one(u) for u in urls))
    finally:
        cache.close()
        if durations:
            stats.p50_ms = round(statistics.median(durations), 1)
            stats.p95_ms = round(sorted(durations)[max(0, int(len(durations) * 0.95) - 1)], 1)
        stats.finished_at = datetime.now(UTC)
        if store is not None:
            store.finish(stats)
    return stats, records
