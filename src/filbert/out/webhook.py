"""ارسال `PageRecord` به یک URL (پنل SEO): دسته‌ای، با retry نمایی و امضای HMAC-SHA256 اختیاری."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging

import httpx
import orjson

from filbert.models import PageRecord

log = logging.getLogger(__name__)


class WebhookSender:
    def __init__(
        self,
        url: str,
        *,
        secret: str | None = None,
        batch_size: int = 10,
        timeout: float = 30.0,
        retries: int = 3,
        run_id: str = "-",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url
        self.secret = secret
        self.batch_size = max(1, batch_size)
        self.timeout = timeout
        self.retries = retries
        self.run_id = run_id
        self._client = client
        self._own_client = client is None
        self._buf: list[PageRecord] = []
        self.stats = {"sent": 0, "batches": 0, "failed_batches": 0}

    async def __aenter__(self) -> WebhookSender:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.flush()
        if self._own_client and self._client is not None:
            await self._client.aclose()

    def _sign(self, body: bytes) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": "filbert-webhook"}
        if self.secret:
            sig = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
            headers["X-Filbert-Signature"] = f"sha256={sig}"
        return headers

    async def add(self, rec: PageRecord) -> None:
        self._buf.append(rec)
        if len(self._buf) >= self.batch_size:
            await self.flush()

    async def flush(self) -> None:
        if not self._buf or self._client is None:
            return
        batch, self._buf = self._buf, []
        body = orjson.dumps(
            {
                "run_id": self.run_id,
                "count": len(batch),
                "records": [r.model_dump(mode="json") for r in batch],
            }
        )
        delay = 0.5
        for attempt in range(1, self.retries + 2):
            try:
                resp = await self._client.post(self.url, content=body, headers=self._sign(body))
                if resp.status_code < 300:
                    self.stats["sent"] += len(batch)
                    self.stats["batches"] += 1
                    return
                if resp.status_code < 500 and resp.status_code != 429:
                    log.warning("webhook %s: http %s (no retry)", self.url, resp.status_code)
                    break
                log.warning("webhook %s: http %s (attempt %d)", self.url, resp.status_code, attempt)
            except httpx.HTTPError as e:
                log.warning("webhook %s: %s (attempt %d)", self.url, e, attempt)
            if attempt <= self.retries:
                await asyncio.sleep(delay)
                delay *= 4
        self.stats["failed_batches"] += 1
