"""کشف URL برای ساخت دیتاست: sitemap (با index بازگشتی)، صفحه فهرست (لینک‌های هم‌دامنه با الگو)، یا فهرست صریح."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from filbert.config import Settings
from filbert.extract.domtext import parse
from filbert.fetch.client import Fetcher, FetchError
from filbert.fetch.urlnorm import normalize_url, registered_domain

log = logging.getLogger("bench.discover")
_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)
_SITEMAP_TAG_RE = re.compile(r"<sitemap>", re.IGNORECASE)


async def _get(fetcher: Fetcher, url: str) -> str | None:
    try:
        return (await fetcher.fetch(url)).text
    except FetchError as e:
        log.warning("discover: %s", e)
        return None


async def from_sitemap(
    fetcher: Fetcher, url: str, pattern: str, exclude: str | None, limit: int, depth: int = 2
) -> list[str]:
    body = await _get(fetcher, url)
    if body is None:
        return []
    locs = [loc.strip() for loc in _LOC_RE.findall(body)]
    pat, exc = re.compile(pattern), (re.compile(exclude) if exclude else None)
    found: list[str] = []
    if _SITEMAP_TAG_RE.search(body) and depth > 0:
        # sitemap index: زیرسایت‌مپ‌ها — جدیدترین‌ها معمولاً آخرند؛ از آخر شروع می‌کنیم
        for sub in reversed(locs):
            found += await from_sitemap(
                fetcher, sub, pattern, exclude, limit - len(found), depth - 1
            )
            if len(found) >= limit:
                break
        return found[:limit]
    for u in locs:
        if pat.search(u) and not (exc and exc.search(u)):
            found.append(normalize_url(u))
            if len(found) >= limit:
                break
    return found


async def from_listing(
    fetcher: Fetcher, url: str, pattern: str, exclude: str | None, limit: int
) -> list[str]:
    body = await _get(fetcher, url)
    if body is None:
        return []
    tree = parse(body)
    pat, exc = re.compile(pattern), (re.compile(exclude) if exclude else None)
    host_dom = registered_domain(urlsplit(url).hostname or "")
    seen: set[str] = set()
    out: list[str] = []
    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        u = normalize_url(href, base=url)
        if registered_domain(urlsplit(u).hostname or "") != host_dom:
            continue
        if u in seen or not pat.search(u) or (exc and exc.search(u)) or u == normalize_url(url):
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= limit:
            break
    return out


async def discover(source: dict, settings: Settings, limit: int) -> list[str]:
    """`source["discover"]` = {sitemap|listing|urls, pattern, exclude}"""
    d = source["discover"]
    if "urls" in d:
        return [normalize_url(u) for u in d["urls"]][:limit]
    async with Fetcher(settings) as f:
        if "sitemap" in d:
            return await from_sitemap(
                f, d["sitemap"], d.get("pattern", "."), d.get("exclude"), limit
            )
        urls: list[str] = []
        for page in d["listing"] if isinstance(d["listing"], list) else [d["listing"]]:
            urls += [
                u
                for u in await from_listing(f, page, d.get("pattern", "."), d.get("exclude"), limit)
                if u not in urls
            ]
            if len(urls) >= limit:
                break
        return urls[:limit]
