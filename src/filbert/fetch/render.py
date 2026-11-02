"""استخر Playwright برای رندر مشروط (اختیاری، extras `[render]`).

- Chromium headless، ۲–۴ context همزمان، بلاک تصویر/فونت/مدیا/استایل، `domcontentloaded` سپس
  `networkidle` با سقف (پیش‌فرض 10s)، ری‌استارت پیشگیرانه هر N صفحه و بازیابی پس از کرش.
- خروجی HTML رندرشده؛ ذخیره در کش با `rendered=true` بر عهده pipeline است.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)
BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font", "stylesheet"})


class RenderUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class RenderResult:
    url: str
    final_url: str
    status: int | None
    html: str
    ms: int


class RenderPool:
    def __init__(
        self,
        *,
        contexts: int = 3,
        timeout_s: float = 10.0,
        restart_every: int = 200,
        user_agent: str | None = None,
        locale: str = "fa-IR",
        headless: bool = True,
    ) -> None:
        self.contexts = contexts
        self.timeout_s = timeout_s
        self.restart_every = restart_every
        self.user_agent = user_agent
        self.locale = locale
        self.headless = headless
        self._pw: Any = None
        self._browser: Any = None
        self._sem = asyncio.Semaphore(contexts)
        self._lock = asyncio.Lock()
        self._pages_since_restart = 0
        self.stats = {"ok": 0, "failed": 0, "timeouts": 0, "restarts": 0, "crashes": 0}

    async def __aenter__(self) -> RenderPool:
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:  # pragma: no cover
            raise RenderUnavailable(
                "playwright not installed: uv sync --extra render && uv run playwright install chromium"
            ) from e
        self._pw = await async_playwright().start()
        await self._launch()
        return self

    async def _launch(self) -> None:
        try:
            self._browser = await self._pw.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    f"--lang={self.locale}",
                ],
            )
        except Exception as e:  # noqa: BLE001
            raise RenderUnavailable(f"chromium launch failed: {e}") from e
        self._pages_since_restart = 0

    async def __aexit__(self, *exc: object) -> None:
        for closer in (self._browser, self._pw):
            if closer is not None:
                with contextlib.suppress(Exception):
                    await (closer.close() if closer is self._browser else closer.stop())
        self._browser = self._pw = None

    async def _get_browser(self) -> Any:
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                if self._browser is not None:
                    self.stats["crashes"] += 1
                await self._launch()
                self.stats["restarts"] += 1
            elif self.restart_every and self._pages_since_restart >= self.restart_every:
                await self._browser.close()
                await self._launch()
                self.stats["restarts"] += 1
            return self._browser

    async def render(self, url: str) -> RenderResult:
        from playwright.async_api import Error as PWError
        from playwright.async_api import TimeoutError as PWTimeout

        t0 = time.perf_counter()
        async with self._sem:
            browser = await self._get_browser()
            context = await browser.new_context(
                user_agent=self.user_agent,
                locale=self.locale,
                viewport={"width": 1280, "height": 900},
            )
            try:
                await context.route(
                    "**/*",
                    lambda route: (
                        route.abort()
                        if route.request.resource_type in BLOCKED_RESOURCE_TYPES
                        else route.continue_()
                    ),
                )
                page = await context.new_page()
                resp = await page.goto(
                    url, wait_until="domcontentloaded", timeout=self.timeout_s * 1000
                )
                with contextlib.suppress(PWTimeout):  # سقف networkidle؛ با آنچه هست ادامه می‌دهیم
                    await page.wait_for_load_state("networkidle", timeout=self.timeout_s * 1000)
                html = await page.content()
                self.stats["ok"] += 1
                return RenderResult(
                    url=url,
                    final_url=page.url,
                    status=resp.status if resp else None,
                    html=html,
                    ms=int((time.perf_counter() - t0) * 1000),
                )
            except PWTimeout as e:
                self.stats["timeouts"] += 1
                self.stats["failed"] += 1
                raise TimeoutError(f"render timeout: {url}") from e
            except PWError as e:
                self.stats["failed"] += 1
                raise RuntimeError(f"render failed: {url}: {str(e).splitlines()[0]}") from e
            finally:
                with contextlib.suppress(Exception):
                    await context.close()
                self._pages_since_restart += 1
