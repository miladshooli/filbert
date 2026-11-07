"""محافظ SSRF: سروری که برای دیگران URL می‌گیرد نباید به شبکه داخلی خودش درخواست بزند.

- فقط `http`/`https`؛ نام‌های `localhost`، `*.local`، `*.internal` و هر IP غیرعمومی
  (خصوصی، loopback، link-local مثل `169.254.169.254`، multicast، رزرو) رد می‌شوند.
- نام دامنه resolve می‌شود و **همه** آدرس‌هایش باید عمومی باشند؛ نتیجه ۶۰ ثانیه کش می‌شود.
- روی هر درخواست httpx (از جمله هر redirect) و هر درخواست مرورگر رندر اجرا می‌شود.
- محدودیت: DNS rebinding بین بررسی و اتصال را کامل نمی‌بندد؛ برای سرور عمومی، فایروال خروجی
  کانتینر را هم ببندید (docs/API.md).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlsplit

import httpx

ALLOWED_SCHEMES = frozenset({"http", "https"})
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")
_TTL_S = 60.0


class URLNotAllowed(ValueError):
    """URL به مقصد غیرمجاز (شبکه داخلی یا scheme غیر HTTP) اشاره می‌کند."""


def ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


class URLGuard:
    def __init__(self, *, allow_private: bool = False) -> None:
        self.allow_private = allow_private
        self._cache: dict[tuple[str, int], tuple[float, str | None]] = {}

    async def check(self, url: str) -> None:
        """URL مجاز نباشد → `URLNotAllowed`. خطای DNS را رد نمی‌کند (دریافت خودش شکست می‌خورد)."""
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            raise URLNotAllowed(f"scheme not allowed: {scheme or '-'}")
        host = (parts.hostname or "").rstrip(".").lower()
        if not host:
            raise URLNotAllowed("missing host")
        if self.allow_private:
            return
        port = parts.port or (443 if scheme == "https" else 80)
        key = (host, port)
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit is not None and now - hit[0] < _TTL_S:
            reason = hit[1]
        else:
            reason = await self._evaluate(host, port)
            self._cache[key] = (now, reason)
        if reason is not None:
            raise URLNotAllowed(reason)

    async def _evaluate(self, host: str, port: int) -> str | None:
        if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
            return f"private host: {host}"
        try:
            literal = ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            literal = None
        if literal is not None:
            return None if ip_is_public(literal) else f"private address: {literal}"
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
        except OSError:
            return None  # resolve نشد؛ httpx هم وصل نمی‌شود و خطای شبکه برمی‌گرداند
        for info in infos:
            addr = ipaddress.ip_address(info[4][0].split("%", 1)[0])
            if not ip_is_public(addr):
                return f"{host} resolves to private address {addr}"
        return None

    async def httpx_hook(self, request: httpx.Request) -> None:
        """event hook برای `httpx.AsyncClient`؛ روی هر redirect هم صدا زده می‌شود."""
        await self.check(str(request.url))

    async def allows(self, url: str) -> bool:
        try:
            await self.check(url)
        except URLNotAllowed:
            return False
        return True
