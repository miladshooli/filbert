#!/usr/bin/env python3
"""
تست پایداری Playwright برای filbert — اجرا روی ویندوز، پشت VPN.

هدف: ۲ ساعت رندر پیوسته با استخر چند context و ثبت
نرخ موفقیت، تأخیر p50/p95، تعداد کرش/ری‌استارت مرورگر، و مصرف حافظه.

نصب (PowerShell):
    pip install playwright psutil
    playwright install chromium

اجرا:
    python playwright_stability_test.py --urls urls.txt --hours 2 --contexts 3
    python playwright_stability_test.py --urls urls.txt --minutes 10 --contexts 2   # تست کوتاه اول

خروجی‌ها (در پوشه stability_out/):
    log.csv       یک خط به‌ازای هر رندر
    summary.json  جمع‌بندی نهایی
    summary.md    همان جمع‌بندی برای چسباندن در سند
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil  # اختیاری؛ برای حافظه
except ImportError:  # pragma: no cover
    psutil = None

from playwright.async_api import async_playwright, Browser, Error as PWError, TimeoutError as PWTimeout

BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

DEFAULT_URLS = [
    "https://nobitex.ir/",
    "https://nobitex.ir/blog/",
    "https://www.digikala.com/",
    "https://www.zoomit.ir/",
    "https://www.isna.ir/",
    "https://www.varzesh3.com/",
    "https://virgool.io/",
    "https://fa.wikipedia.org/wiki/%D8%AA%D9%87%D8%B1%D8%A7%D9%86",
]


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, round((p / 100) * (len(s) - 1))))
    return s[k]


class Stats:
    def __init__(self) -> None:
        self.ok = 0
        self.fail = 0
        self.timeouts = 0
        self.crashes = 0
        self.restarts = 0
        self.latencies_ms: list[float] = []
        self.text_lens: list[int] = []
        self.errors: dict[str, int] = {}
        self.mem_samples_mb: list[float] = []
        self.start = time.time()

    def record_error(self, kind: str) -> None:
        self.errors[kind] = self.errors.get(kind, 0) + 1


class BrowserManager:
    """یک مرورگر مشترک؛ در صورت کرش یا هر N صفحه، ری‌استارت می‌شود."""

    def __init__(self, pw, stats: Stats, headless: bool, restart_every: int) -> None:
        self.pw = pw
        self.stats = stats
        self.headless = headless
        self.restart_every = restart_every
        self.browser: Browser | None = None
        self.pages_since_restart = 0
        self.lock = asyncio.Lock()

    async def launch(self) -> None:
        self.browser = await self.pw.chromium.launch(
            headless=self.headless,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage", "--lang=fa-IR"],
        )
        self.pages_since_restart = 0

    async def get(self) -> Browser:
        async with self.lock:
            if self.browser is None or not self.browser.is_connected():
                if self.browser is not None:
                    self.stats.crashes += 1
                await self.launch()
                self.stats.restarts += 1
            elif self.restart_every and self.pages_since_restart >= self.restart_every:
                await self.browser.close()
                await self.launch()
                self.stats.restarts += 1
            return self.browser

    async def close(self) -> None:
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                pass

    def browser_rss_mb(self) -> float | None:
        if psutil is None:
            return None
        total = 0
        for p in psutil.process_iter(["name", "memory_info"]):
            try:
                n = (p.info["name"] or "").lower()
                if "chrome" in n or "chromium" in n or "headless_shell" in n:
                    total += p.info["memory_info"].rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return round(total / 1024 / 1024, 1) if total else None


async def render_one(mgr: BrowserManager, url: str, timeout_s: float, writer, stats: Stats) -> None:
    t0 = time.perf_counter()
    status = ""
    err_kind = ""
    text_len = 0
    html_len = 0
    try:
        browser = await mgr.get()
        context = await browser.new_context(
            user_agent=UA,
            locale="fa-IR",
            viewport={"width": 1280, "height": 900},
            java_script_enabled=True,
        )
        try:
            await context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in BLOCKED_RESOURCE_TYPES
                else route.continue_(),
            )
            page = await context.new_page()
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
            try:
                await page.wait_for_load_state("networkidle", timeout=timeout_s * 1000)
            except PWTimeout:
                pass  # networkidle سقف دارد؛ ادامه می‌دهیم
            status = str(resp.status) if resp else "no-response"
            html = await page.content()
            html_len = len(html)
            text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            text_len = len(text)
            stats.ok += 1
            stats.text_lens.append(text_len)
        finally:
            await context.close()
            mgr.pages_since_restart += 1
    except PWTimeout:
        err_kind = "timeout"
        stats.timeouts += 1
        stats.fail += 1
        stats.record_error(err_kind)
    except PWError as e:
        msg = str(e).split("\n", 1)[0]
        err_kind = "pw:" + msg[:80]
        stats.fail += 1
        stats.record_error(err_kind)
    except Exception as e:  # noqa: BLE001
        err_kind = type(e).__name__ + ":" + str(e)[:80]
        stats.fail += 1
        stats.record_error(err_kind)

    ms = (time.perf_counter() - t0) * 1000
    stats.latencies_ms.append(ms)
    writer.writerow(
        [datetime.now(timezone.utc).isoformat(timespec="seconds"), url, status, round(ms), html_len, text_len, err_kind]
    )


async def worker(name: int, mgr: BrowserManager, urls: list[str], deadline: float, timeout_s: float, writer, stats: Stats, pause: float):
    i = name
    while time.time() < deadline:
        url = urls[i % len(urls)]
        i += random.randint(1, 3)
        await render_one(mgr, url, timeout_s, writer, stats)
        await asyncio.sleep(pause + random.random() * pause)


async def reporter(mgr: BrowserManager, stats: Stats, deadline: float, every_s: int):
    while time.time() < deadline:
        await asyncio.sleep(every_s)
        mem = mgr.browser_rss_mb()
        if mem is not None:
            stats.mem_samples_mb.append(mem)
        done = stats.ok + stats.fail
        rate = (stats.ok / done * 100) if done else 0
        elapsed = int(time.time() - stats.start)
        print(
            f"[{elapsed//60:3d}m] done={done} ok={stats.ok} fail={stats.fail} "
            f"timeouts={stats.timeouts} restarts={stats.restarts} crashes={stats.crashes} "
            f"p50={pct(stats.latencies_ms, 50) and round(pct(stats.latencies_ms, 50))}ms "
            f"p95={pct(stats.latencies_ms, 95) and round(pct(stats.latencies_ms, 95))}ms "
            f"mem={mem}MB ok%={rate:.1f}",
            flush=True,
        )


async def main_async(args: argparse.Namespace) -> int:
    urls = DEFAULT_URLS
    if args.urls:
        urls = [u.strip() for u in Path(args.urls).read_text(encoding="utf-8").splitlines() if u.strip() and not u.startswith("#")]
    if not urls:
        print("هیچ URL ای پیدا نشد.", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    duration_s = args.hours * 3600 + args.minutes * 60
    deadline = time.time() + duration_s
    stats = Stats()

    print(f"شروع: {len(urls)} URL، {args.contexts} context همزمان، {duration_s//60} دقیقه، timeout={args.timeout}s", flush=True)

    with open(out / "log.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["ts_utc", "url", "status", "ms", "html_len", "text_len", "error"])
        async with async_playwright() as pw:
            mgr = BrowserManager(pw, stats, headless=not args.headed, restart_every=args.restart_every)
            await mgr.launch()
            tasks = [
                asyncio.create_task(worker(i, mgr, urls, deadline, args.timeout, writer, stats, args.pause))
                for i in range(args.contexts)
            ]
            tasks.append(asyncio.create_task(reporter(mgr, stats, deadline, args.report_every)))
            try:
                await asyncio.gather(*tasks)
            finally:
                await mgr.close()

    done = stats.ok + stats.fail
    summary = {
        "started_at": datetime.fromtimestamp(stats.start, tz=timezone.utc).isoformat(timespec="seconds"),
        "duration_min": round(duration_s / 60),
        "contexts": args.contexts,
        "urls": len(urls),
        "pages_total": done,
        "pages_ok": stats.ok,
        "pages_failed": stats.fail,
        "success_rate_pct": round(stats.ok / done * 100, 2) if done else None,
        "timeouts": stats.timeouts,
        "browser_crashes": stats.crashes,
        "browser_restarts": stats.restarts,
        "latency_ms": {
            "p50": pct(stats.latencies_ms, 50) and round(pct(stats.latencies_ms, 50)),
            "p95": pct(stats.latencies_ms, 95) and round(pct(stats.latencies_ms, 95)),
            "max": round(max(stats.latencies_ms)) if stats.latencies_ms else None,
        },
        "pages_per_minute": round(done / (duration_s / 60), 2) if duration_s else None,
        "text_len_median": int(statistics.median(stats.text_lens)) if stats.text_lens else None,
        "browser_mem_mb": {
            "min": min(stats.mem_samples_mb) if stats.mem_samples_mb else None,
            "max": max(stats.mem_samples_mb) if stats.mem_samples_mb else None,
        },
        "errors": dict(sorted(stats.errors.items(), key=lambda kv: -kv[1])[:15]),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "| معیار | مقدار |",
        "| --- | --- |",
        f"| مدت (دقیقه) | {summary['duration_min']} |",
        f"| context همزمان | {summary['contexts']} |",
        f"| صفحات رندرشده | {summary['pages_total']} |",
        f"| نرخ موفقیت | {summary['success_rate_pct']}% |",
        f"| timeout | {summary['timeouts']} |",
        f"| کرش مرورگر | {summary['browser_crashes']} |",
        f"| ری‌استارت مرورگر | {summary['browser_restarts']} |",
        f"| p50 / p95 / max (ms) | {summary['latency_ms']['p50']} / {summary['latency_ms']['p95']} / {summary['latency_ms']['max']} |",
        f"| صفحه در دقیقه | {summary['pages_per_minute']} |",
        f"| حافظه مرورگر min / max (MB) | {summary['browser_mem_mb']['min']} / {summary['browser_mem_mb']['max']} |",
    ]
    (out / "summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print("\n".join(md))
    print(f"\nخروجی‌ها در: {out.resolve()}")

    verdict_ok = (summary["success_rate_pct"] or 0) >= 97 and summary["browser_crashes"] <= 2
    print("\nنتیجه:", "پایدار ✔ — Playwright مشروط در فاز ۴ قابل استفاده است." if verdict_ok else "ناپایدار ✘ — contexts را کم کنید یا restart-every را پایین بیاورید و دوباره تست کنید.")
    return 0 if verdict_ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="تست پایداری Playwright برای filbert")
    ap.add_argument("--urls", help="فایل متنی، هر خط یک URL (پیش‌فرض: چند سایت فارسی)")
    ap.add_argument("--hours", type=float, default=0)
    ap.add_argument("--minutes", type=float, default=0)
    ap.add_argument("--contexts", type=int, default=3, help="تعداد context همزمان (۲ تا ۴ پیشنهاد سند)")
    ap.add_argument("--timeout", type=float, default=10.0, help="سقف ثانیه برای هر صفحه")
    ap.add_argument("--pause", type=float, default=0.5, help="مکث بین صفحات هر worker (ثانیه)")
    ap.add_argument("--restart-every", type=int, default=200, help="ری‌استارت پیشگیرانه مرورگر هر N صفحه (0 = خاموش)")
    ap.add_argument("--report-every", type=int, default=60, help="فاصله گزارش کنسول (ثانیه)")
    ap.add_argument("--headed", action="store_true", help="نمایش مرورگر (برای دیباگ)")
    ap.add_argument("--out", default="stability_out")
    args = ap.parse_args()
    if args.hours == 0 and args.minutes == 0:
        args.hours = 2.0

    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
