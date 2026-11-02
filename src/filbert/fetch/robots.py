"""احترام به `robots.txt`: یک بار در هر دامنه، کش ۲۴ ساعته در حافظه و دیسک (`cache_dir/robots/`)."""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

log = logging.getLogger(__name__)
TTL_SECONDS = 24 * 3600


class RobotsCache:
    def __init__(
        self, cache_dir: Path | None, *, user_agent: str = "*", ttl: int = TTL_SECONDS
    ) -> None:
        self.dir = (Path(cache_dir) / "robots") if cache_dir else None
        if self.dir is not None:
            self.dir.mkdir(parents=True, exist_ok=True)
        self.ua = user_agent
        self.ttl = ttl
        self._mem: dict[str, tuple[float, RobotFileParser | None]] = {}

    @staticmethod
    def _origin(url: str) -> str:
        p = urlsplit(url)
        return f"{p.scheme}://{p.netloc}"

    def _disk_path(self, origin: str) -> Path | None:
        if self.dir is None:
            return None
        return self.dir / (hashlib.sha256(origin.encode()).hexdigest()[:24] + ".txt")

    def _parse(self, text: str) -> RobotFileParser:
        rp = RobotFileParser()
        rp.parse(text.splitlines())
        return rp

    async def _load(self, client: httpx.AsyncClient, origin: str) -> RobotFileParser | None:
        """None = robots.txt در دسترس نیست (همه مجاز)."""
        now = time.time()
        hit = self._mem.get(origin)
        if hit and now - hit[0] < self.ttl:
            return hit[1]
        disk = self._disk_path(origin)
        if disk is not None and disk.exists() and now - disk.stat().st_mtime < self.ttl:
            rp = self._parse(disk.read_text(encoding="utf-8", errors="replace"))
            self._mem[origin] = (now, rp)
            return rp
        rp: RobotFileParser | None = None
        try:
            resp = await client.get(
                f"{origin}/robots.txt",
                headers={"User-Agent": self.ua if self.ua != "*" else "filbert"},
            )
            if (
                resp.status_code == 200
                and "html" not in (resp.headers.get("content-type") or "").lower()
            ):
                text = resp.text
                rp = self._parse(text)
                if disk is not None:
                    disk.write_text(text, encoding="utf-8")
            elif resp.status_code in (401, 403):
                rp = self._parse("User-agent: *\nDisallow: /")  # طبق RFC 9309: دسترسی ممنوع
        except httpx.HTTPError as e:
            log.debug("robots %s: %s", origin, e)
        self._mem[origin] = (now, rp)
        return rp

    async def allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        rp = await self._load(client, self._origin(url))
        if rp is None:
            return True
        return rp.can_fetch(self.ua, url)

    async def crawl_delay(self, client: httpx.AsyncClient, url: str) -> float | None:
        rp = await self._load(client, self._origin(url))
        if rp is None:
            return None
        d = rp.crawl_delay(self.ua)
        return float(d) if d else None
