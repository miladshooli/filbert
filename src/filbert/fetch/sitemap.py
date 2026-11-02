"""خواندن sitemap و sitemap index (بازگشتی، با gzip) → فهرست URL نرمال‌شده."""

from __future__ import annotations

import gzip
import logging
import re
from collections.abc import Iterable

from filbert.fetch.client import Fetcher, FetchError
from filbert.fetch.urlnorm import normalize_url

log = logging.getLogger(__name__)
_LOC_RE = re.compile(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\s\]]+)\s*(?:\]\]>)?\s*</loc>", re.IGNORECASE)
_INDEX_RE = re.compile(r"<sitemapindex\b|<sitemap\b", re.IGNORECASE)
_LASTMOD_RE = re.compile(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", re.IGNORECASE)


def parse_sitemap(text: str) -> tuple[list[str], bool]:
    """(locها، آیا index است)"""
    locs = [m.group(1).strip() for m in _LOC_RE.finditer(text)]
    return locs, bool(_INDEX_RE.search(text))


async def _get_text(fetcher: Fetcher, url: str) -> str | None:
    try:
        r = await fetcher.fetch(url)
    except FetchError as e:
        log.warning("sitemap %s: %s", url, e.reason)
        return None
    body = r.body
    if url.lower().endswith(".gz") or body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError:
            return None
        return body.decode("utf-8", "replace")
    return r.text


async def urls_from_sitemap(
    fetcher: Fetcher,
    sitemap_url: str,
    *,
    limit: int = 10_000,
    pattern: str | None = None,
    exclude: str | None = None,
    max_depth: int = 3,
    newest_first: bool = True,
) -> list[str]:
    pat = re.compile(pattern) if pattern else None
    exc = re.compile(exclude) if exclude else None
    seen: set[str] = set()
    out: list[str] = []

    async def walk(url: str, depth: int) -> None:
        if len(out) >= limit or depth > max_depth:
            return
        text = await _get_text(fetcher, url)
        if text is None:
            return
        locs, is_index = parse_sitemap(text)
        if is_index:
            for sub in reversed(locs) if newest_first else locs:
                await walk(sub, depth + 1)
                if len(out) >= limit:
                    return
            return
        for loc in locs:
            if pat and not pat.search(loc):
                continue
            if exc and exc.search(loc):
                continue
            u = normalize_url(loc)
            if u in seen:
                continue
            seen.add(u)
            out.append(u)
            if len(out) >= limit:
                return

    await walk(sitemap_url, 0)
    return out


def read_url_file(lines: Iterable[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(normalize_url(s))
    return out
