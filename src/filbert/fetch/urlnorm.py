"""نرمال‌سازی URL و تشخیص لینک داخلی/خارجی با eTLD+1.

نرمال‌سازی: حذف پارامترهای ردیابی، مرتب‌سازی query، حذف fragment، lowercase کردن
scheme/host، حذف پورت پیش‌فرض، حذف `index.html` انتهایی. اسلش انتهایی دست نمی‌خورد
(فقط مسیر خالی → `/`).
"""

from __future__ import annotations

import contextlib
import re
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import tldextract

TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "fbclid",
        "gclid",
        "yclid",
        "dclid",
        "msclkid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
        "ref_url",
        "_ga",
        "_gl",
        "spm",
        "zanpid",
        "mkt_tok",
    }
)
TRACKING_PREFIXES: tuple[str, ...] = ("utm_",)
_INDEX_RE = re.compile(r"/index\.(?:html?|php|aspx?)$", re.IGNORECASE)
_DEFAULT_PORTS = {"http": "80", "https": "443"}

# فهرست پسوندها از نسخه همراه بسته خوانده می‌شود؛ هیچ درخواست شبکه‌ای (پشت VPN) انجام نمی‌شود.
_extract = tldextract.TLDExtract(
    suffix_list_urls=(), fallback_to_snapshot=True, include_psl_private_domains=True
)


def is_tracking_param(name: str) -> bool:
    n = name.lower()
    return n in TRACKING_PARAMS or n.startswith(TRACKING_PREFIXES)


def normalize_url(url: str, base: str | None = None) -> str:
    """URL را نرمال می‌کند؛ اگر `base` داده شود، لینک نسبی اول مطلق می‌شود."""
    url = url.strip()
    if base:
        url = urljoin(base, url)
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    if any(ord(c) > 127 for c in host):
        with contextlib.suppress(UnicodeError):
            host = host.encode("idna").decode("ascii")
    netloc = host
    if parts.port is not None and str(parts.port) != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"
    if parts.username:
        cred = parts.username + (f":{parts.password}" if parts.password else "")
        netloc = f"{cred}@{netloc}"

    path = parts.path or "/"
    path = _INDEX_RE.sub("/", path)
    if not path.startswith("/"):
        path = "/" + path

    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not is_tracking_param(k)
    ]
    query_pairs.sort()
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


@lru_cache(maxsize=4096)
def registered_domain(url_or_host: str) -> str:
    """eTLD+1 (مثلاً `nobitex.ir` برای `https://blog.nobitex.ir/x`)."""
    ext = _extract(url_or_host)
    if ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    return (ext.domain or url_or_host).lower()


def is_internal(url: str, page_url: str) -> bool:
    """لینک داخلی است اگر eTLD+1 با صفحه یکی باشد (زیردامنه‌ها داخلی حساب می‌شوند)."""
    host_a = urlsplit(url).hostname
    host_b = urlsplit(page_url).hostname
    if not host_a or not host_b:
        return True  # لینک نسبی
    return registered_domain(host_a) == registered_domain(host_b)
