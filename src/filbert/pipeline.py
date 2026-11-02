"""اتصال لایه‌ها: fetch → parse (یک بار) → meta → preclean → readability → نرمال‌سازی → PageRecord.

`extract_html` خالص و همزمان است (بدون شبکه)؛ `fetch_and_extract` async است و خروجی را روی دیسک می‌نویسد.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import statistics
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from filbert import __version__
from filbert.config import Settings
from filbert.extract import ensemble
from filbert.extract.cleanhtml import build_article
from filbert.extract.domtext import node_text, parse
from filbert.extract.markdown import block_to_markdown
from filbert.extract.preclean import preclean
from filbert.extract.rules import load_rules
from filbert.fa.normalize import normalize_text
from filbert.fa.tokenize import char_count, reading_time_min, word_count
from filbert.fetch.cache import Cache
from filbert.fetch.client import Fetcher, FetchError, FetchResult, decode_body, detect_encoding
from filbert.fetch.needs_js import needs_js
from filbert.fetch.robots import RobotsCache
from filbert.fetch.urlnorm import normalize_url
from filbert.meta import structure
from filbert.meta.enrich import enrich_head, finish
from filbert.meta.head import extract_head
from filbert.models import Content, HttpInfo, PageRecord, RunStats
from filbert.out.common import direction_for
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
    rec.content.markdown = markdown_body(res.raw_blocks, final)
    return rec


def markdown_body(raw_blocks: list, base_url: str | None) -> str:
    parts = [block_to_markdown(b.node, b.type, base_url) for b in raw_blocks]
    return "\n\n".join(p for p in parts if p).strip() + "\n"


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
    """استخراج همزمان از نتیجه دریافت (بدون ProcessPool)."""
    job = _job_from_fetch(fr, cache, rendered=False)
    return extract_html(
        job["html"],
        job["url"],
        settings=settings,
        final_url=job["final_url"],
        http=HttpInfo.model_validate(job["http"]),
        response_headers=job["headers"],
        fetched_at=fr.fetched_at,
        raw_html_ref=job["raw_html_ref"],
    )


def is_url(s: str) -> bool:
    return s.lower().startswith(("http://", "https://"))


_WORKER_SETTINGS: Settings | None = None


def _worker_init(settings_dump: dict) -> None:
    global _WORKER_SETTINGS
    _WORKER_SETTINGS = Settings(**settings_dump, _env_file=None)


def _extract_job(job: dict) -> PageRecord:
    """اجرا در پردازه کارگر: ورودی/خروجی picklable."""
    settings = _WORKER_SETTINGS or Settings(_env_file=None)
    return extract_html(
        job["html"],
        job["url"],
        settings=settings,
        final_url=job["final_url"],
        http=HttpInfo.model_validate(job["http"]),
        response_headers=job["headers"],
        fetched_at=datetime.fromisoformat(job["fetched_at"]) if job["fetched_at"] else None,
        raw_html_ref=job["raw_html_ref"],
    )


def _job_from_fetch(
    fr: FetchResult, cache: Cache | None, *, rendered: bool, html: str | None = None
) -> dict:
    http = HttpInfo(
        status=fr.status,
        content_type=fr.headers.get("content-type"),
        content_length=len(fr.body),
        response_ms=fr.response_ms,
        redirects=fr.redirects,
        rendered=rendered,
        last_modified=fr.headers.get("last-modified"),
        etag=fr.headers.get("etag"),
        detected_encoding=fr.encoding,
        from_cache=fr.from_cache,
    )
    return {
        "html": html if html is not None else fr.text,
        "url": fr.url,
        "final_url": fr.final_url,
        "http": http.model_dump(mode="json"),
        "headers": dict(fr.headers),
        "fetched_at": fr.fetched_at.isoformat() if fr.fetched_at else None,
        "raw_html_ref": cache.raw_ref(fr.raw_key) if (cache is not None and fr.raw_key) else None,
    }


def _pool_size(settings: Settings, n_urls: int) -> int:
    if n_urls < 4:
        return 0
    w = settings.workers if settings.workers is not None else (os.cpu_count() or 1)
    return 0 if w <= 1 else w


async def fetch_and_extract(
    inputs: list[str],
    *,
    settings: Settings | None = None,
    out_dir: Path | None = None,
    formats: tuple[str, ...] = FORMATS,
    force: bool = False,
    only_changed: bool = False,
    on_result: ProgressCallback | None = None,
) -> tuple[RunStats, list[PageRecord]]:
    """URLها/فایل‌ها را می‌گیرد، استخراج می‌کند و (اگر `out_dir` داده شود) روی دیسک می‌نویسد.

    دریافت async؛ استخراج در ProcessPool (برای ≥۴ URL و `workers>1`)؛ رندر مشروط با Playwright
    (`settings.render`)؛ `only_changed`: صفحاتی که `content_hash`شان با ایندکس کش یکی است نوشته نمی‌شوند.
    """
    settings = settings or Settings()
    started = datetime.now(UTC)
    store = Store(out_dir, formats=formats) if out_dir is not None else None
    run_id = store.run_id if store else "-"
    stats = RunStats(
        run_id=run_id,
        tool_version=__version__,
        started_at=started,
        settings={
            "formats": list(formats),
            "force": force,
            "only_changed": only_changed,
            "render": settings.render,
            "workers": settings.workers,
            "concurrency": settings.concurrency,
            "cache_dir": str(settings.cache_dir),
            "respect_robots": settings.respect_robots,
        },
        n=len(inputs),
    )
    records: list[PageRecord] = []
    durations: list[float] = []
    cache = Cache(settings.cache_dir)
    loop = asyncio.get_running_loop()

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
    pool: ProcessPoolExecutor | None = None
    n_workers = _pool_size(settings, len(urls))
    if n_workers:
        pool = ProcessPoolExecutor(
            max_workers=n_workers,
            initializer=_worker_init,
            initargs=(settings.model_dump(mode="json"),),
        )
    render_pool = None
    robots = RobotsCache(settings.cache_dir) if settings.respect_robots else None
    try:
        if urls and settings.render != "never":
            from filbert.fetch.render import RenderPool, RenderUnavailable

            try:
                render_pool = await RenderPool(
                    contexts=settings.render_contexts,
                    timeout_s=settings.render_timeout,
                    user_agent=settings.user_agents[0],
                ).__aenter__()
            except RenderUnavailable as e:
                log.warning("render disabled: %s", e)
                render_pool = None
        if urls:
            async with Fetcher(settings, cache) as fetcher:

                async def extract(job: dict) -> PageRecord:
                    if pool is None:
                        return _extract_job(job)
                    return await loop.run_in_executor(pool, _extract_job, job)

                async def one(u: str) -> None:
                    t0 = time.perf_counter()
                    if robots is not None and not await robots.allowed(fetcher.client, u):
                        stats.robots_blocked += 1
                        handle(None, u, "robots.txt disallow")
                        return
                    try:
                        fr = await fetcher.fetch(u, force=force)
                    except FetchError as e:
                        handle(None, u, e.reason)
                        return
                    rendered = False
                    html: str | None = None
                    if render_pool is not None:
                        want = settings.render == "always" or (
                            settings.render == "auto"
                            and needs_js(
                                fr.text,
                                parse(fr.text),
                                fr.final_url,
                                frozenset(settings.always_render_domains),
                            ).needs_js
                        )
                        if want:
                            try:
                                rr = await render_pool.render(fr.final_url)
                                html, rendered = rr.html, True
                                cache.store(
                                    fr.url,
                                    rr.html.encode("utf-8"),
                                    final_url=rr.final_url,
                                    status=rr.status or fr.status,
                                    headers=fr.headers,
                                    encoding="utf-8",
                                    rendered=True,
                                    fetched_at=fr.fetched_at,
                                )
                                stats.rendered += 1
                            except (TimeoutError, RuntimeError) as e:
                                log.warning("render %s: %s", u, e)
                    try:
                        rec = await extract(
                            _job_from_fetch(fr, cache, rendered=rendered, html=html)
                        )
                    except Exception as e:  # noqa: BLE001 — خطای استخراج نباید اجرا را بخواباند
                        log.exception("extract %s failed", u)
                        handle(None, u, f"extract: {type(e).__name__}: {e}")
                        return
                    durations.append((time.perf_counter() - t0) * 1000)
                    if only_changed:
                        entry = cache.index.get(fr.url)
                        if entry is not None and entry.content_hash == rec.content_hash:
                            stats.skipped_unchanged += 1
                            if on_result is not None:
                                on_result(rec, u, None)
                            return
                    cache.index.update_hash(fr.url, rec.content_hash or "", run_id)
                    handle(rec, u, None)

                await asyncio.gather(*(one(u) for u in urls))
    finally:
        if render_pool is not None:
            stats.settings["render_stats"] = dict(render_pool.stats)
            await render_pool.__aexit__(None, None, None)
        if pool is not None:
            pool.shutdown(wait=True)
        cache.close()
        if durations:
            stats.p50_ms = round(statistics.median(durations), 1)
            stats.p95_ms = round(sorted(durations)[max(0, int(len(durations) * 0.95) - 1)], 1)
        stats.finished_at = datetime.now(UTC)
        if store is not None:
            store.finish(stats)
    return stats, records
