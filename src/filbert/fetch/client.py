"""دریافت async با httpx: HTTP/2، محدودیت per-host، retry نمایی، ETag/304 و کش خام.

تنها جایی که I/O شبکه انجام می‌شود.
"""

from __future__ import annotations

import asyncio
import codecs
import logging
import random
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from charset_normalizer import from_bytes

from filbert.config import Settings
from filbert.fetch.cache import Cache, CacheEntry
from filbert.fetch.urlnorm import normalize_url

log = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset=["']?\s*([a-zA-Z0-9_\-]+)""", re.IGNORECASE)
_CT_CHARSET_RE = re.compile(r"charset=\"?([a-zA-Z0-9_\-]+)", re.IGNORECASE)


class FetchError(Exception):
    def __init__(self, url: str, reason: str, status: int | None = None) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason
        self.status = status


@dataclass(slots=True)
class FetchResult:
    url: str  # نرمال‌شده
    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    text: str
    encoding: str
    response_ms: int
    fetched_at: datetime
    redirects: list[str] = field(default_factory=list)
    from_cache: bool = False
    not_modified: bool = False
    raw_key: str | None = None
    attempts: int = 1


class HostLimiter:
    """به‌ازای هر host: حداکثر N درخواست همزمان و دست‌کم `delay` ثانیه فاصله بین شروع‌ها."""

    def __init__(self, concurrency: int, delay_s: float) -> None:
        self._conc = concurrency
        self._delay = delay_s
        self._sems: dict[str, asyncio.Semaphore] = {}
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _sem(self, host: str) -> asyncio.Semaphore:
        if host not in self._sems:
            self._sems[host] = asyncio.Semaphore(self._conc)
            self._locks[host] = asyncio.Lock()
        return self._sems[host]

    async def __call__(self, host: str) -> _HostSlot:
        return _HostSlot(self, host)

    async def _wait_turn(self, host: str) -> None:
        async with self._locks[host]:
            now = time.monotonic()
            wait = self._last.get(host, 0.0) + self._delay - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[host] = time.monotonic()


class _HostSlot:
    def __init__(self, limiter: HostLimiter, host: str) -> None:
        self._l = limiter
        self._host = host
        self._sem = limiter._sem(host)

    async def __aenter__(self) -> None:
        await self._sem.acquire()
        await self._l._wait_turn(self._host)

    async def __aexit__(self, *exc: object) -> None:
        self._sem.release()


def detect_encoding(body: bytes, content_type: str | None) -> str:
    """charset از هدر → `<meta charset>` → charset-normalizer → utf-8."""
    if content_type:
        m = _CT_CHARSET_RE.search(content_type)
        if m:
            return _canon(m.group(1))
    m = _META_CHARSET_RE.search(body[:8192])
    if m:
        return _canon(m.group(1).decode("ascii", "ignore"))
    best = from_bytes(body[:65536]).best()
    if best is not None and best.encoding:
        return _canon(best.encoding)
    return "utf-8"


def _canon(name: str) -> str:
    n = name.strip().lower().replace("_", "-")
    aliases = {"utf8": "utf-8", "cp1256": "windows-1256", "iso-8859-6": "windows-1256"}
    n = aliases.get(n, n)
    try:
        codecs.lookup(n)
    except LookupError:
        return "utf-8"
    return n


def decode_body(body: bytes, encoding: str) -> str:
    text = body.decode(encoding, errors="replace")
    if encoding != "utf-8" and text.count("�") > len(text) // 50:
        # تشخیص اشتباه؛ utf-8 را امتحان کن
        alt = body.decode("utf-8", errors="replace")
        if alt.count("�") < text.count("�"):
            return alt
    return text


class Fetcher:
    """کلاینت مشترک برای یک اجرا. با `async with` استفاده شود."""

    def __init__(self, settings: Settings, cache: Cache | None = None) -> None:
        self.settings = settings
        self.cache = cache
        self._client: httpx.AsyncClient | None = None
        self._limiter = HostLimiter(
            settings.per_host_concurrency, settings.per_host_delay_ms / 1000
        )
        self._global = asyncio.Semaphore(settings.concurrency)

    async def __aenter__(self) -> Fetcher:
        s = self.settings
        self._client = httpx.AsyncClient(
            http2=s.http2,
            follow_redirects=True,
            max_redirects=10,
            timeout=httpx.Timeout(s.total_timeout, connect=s.connect_timeout, read=s.read_timeout),
            limits=httpx.Limits(
                max_connections=s.max_connections,
                max_keepalive_connections=s.max_keepalive_connections,
            ),
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": s.accept_language,
            },
        )
        return self

    @property
    def client(self) -> httpx.AsyncClient:
        assert self._client is not None, "use `async with Fetcher(...)`"
        return self._client

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self, entry: CacheEntry | None) -> dict[str, str]:
        h = {"User-Agent": random.choice(self.settings.user_agents)}
        if entry is not None:
            if entry.etag:
                h["If-None-Match"] = entry.etag
            if entry.last_modified:
                h["If-Modified-Since"] = entry.last_modified
        return h

    async def fetch(self, url: str, *, force: bool = False) -> FetchResult:
        """یک URL را می‌گیرد؛ 304 را از کش برمی‌گرداند؛ روی 429/5xx/timeout retry می‌کند."""
        assert self._client is not None, "use `async with Fetcher(...)`"
        norm = normalize_url(url)
        host = urlsplit(norm).hostname or ""
        entry = None if (force or self.cache is None) else self.cache.lookup(norm)
        backoff = self.settings.retry_backoff
        attempts = len(backoff) + 1
        last_err: str | None = None
        last_status: int | None = None

        for attempt in range(1, attempts + 1):
            t0 = time.perf_counter()
            try:
                async with self._global, await self._limiter(host):
                    resp = await self._client.get(norm, headers=self._headers(entry))
            except httpx.TimeoutException as e:
                last_err = f"timeout: {type(e).__name__}"
            except httpx.HTTPError as e:
                last_err = f"network: {type(e).__name__}: {e}"
            else:
                ms = int((time.perf_counter() - t0) * 1000)
                if resp.status_code in RETRY_STATUSES and attempt <= len(backoff):
                    last_err = f"http {resp.status_code}"
                    last_status = resp.status_code
                    await asyncio.sleep(_retry_delay(resp, backoff[attempt - 1]))
                    continue
                return self._finish(norm, resp, entry, ms, attempt)
            log.warning("fetch %s attempt %d failed: %s", norm, attempt, last_err)
            if attempt <= len(backoff):
                await asyncio.sleep(backoff[attempt - 1])
        raise FetchError(norm, last_err or "unknown", status=last_status)

    def _finish(
        self, norm: str, resp: httpx.Response, entry: CacheEntry | None, ms: int, attempt: int
    ) -> FetchResult:
        headers = {k.lower(): v for k, v in resp.headers.items()}
        redirects = [str(r.url) for r in resp.history]
        now = datetime.now(UTC)

        if resp.status_code == 304 and entry is not None and self.cache is not None:
            body = self.cache.raw.get(entry.raw_key) or b""
            enc = entry.encoding or detect_encoding(body, entry.content_type)
            self.cache.index.touch(norm, now)
            return FetchResult(
                url=norm,
                final_url=entry.final_url or norm,
                status=entry.status or 200,
                headers=headers,
                body=body,
                text=decode_body(body, enc),
                encoding=enc,
                response_ms=ms,
                fetched_at=now,
                redirects=redirects,
                from_cache=True,
                not_modified=True,
                raw_key=entry.raw_key,
                attempts=attempt,
            )

        body = resp.content
        enc = detect_encoding(body, headers.get("content-type"))
        text = decode_body(body, enc)
        raw_key = None
        if self.cache is not None and resp.status_code < 400 and body:
            stored = self.cache.store(
                norm,
                body,
                final_url=str(resp.url),
                status=resp.status_code,
                headers=headers,
                encoding=enc,
                fetched_at=now,
            )
            raw_key = stored.raw_key
        if resp.status_code >= 400:
            raise FetchError(norm, f"http {resp.status_code}", status=resp.status_code)
        return FetchResult(
            url=norm,
            final_url=str(resp.url),
            status=resp.status_code,
            headers=headers,
            body=body,
            text=text,
            encoding=enc,
            response_ms=ms,
            fetched_at=now,
            redirects=redirects,
            raw_key=raw_key,
            attempts=attempt,
        )

    async def fetch_many(self, urls: list[str]) -> list[FetchResult | FetchError]:
        async def one(u: str) -> FetchResult | FetchError:
            try:
                return await self.fetch(u)
            except FetchError as e:
                return e

        return list(await asyncio.gather(*(one(u) for u in urls)))


def _retry_delay(resp: httpx.Response, default: float) -> float:
    ra = resp.headers.get("retry-after")
    if ra and ra.isdigit():
        return min(float(ra), 30.0)
    return default
