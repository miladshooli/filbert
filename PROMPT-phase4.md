فاز ۴ — رندر مشروط و مقیاس (بخش «لایه دریافت» و «کنترل سرعت» BLUEPRINT). معیار خروج: ۳۰۰ صفحه/ثانیه روی کش با ۸ پردازه؛ ۱۰ هزار URL در یک اجرا بدون خطا.

مراحل:
1. `fetch/needs_js.py`: heuristic بدون LLM — متن قابل‌مشاهده body < 400 کاراکتر با HTML > 50KB؛ `#root/#app/#__next` خالی یا فقط `noscript`؛ نسبت بایت script > 0.6؛ دامنه در فهرست «همیشه رندر». تست.
2. `fetch/robots.py`: خواندن `robots.txt` یک بار در هر دامنه، کش ۲۴ ساعته (حافظه + دیسک در cache_dir)، `--ignore-robots`. تست با pytest-httpserver.
3. `fetch/sitemap.py`: sitemap و sitemap index (بازگشتی، gzip)، الگو/exclude، سقف تعداد. تست.
4. `fetch/render.py`: استخر Playwright (Chromium headless، ۲–۴ context، بلاک تصویر/فونت/مدیا، `networkidle` با سقف 10s، ری‌استارت پیشگیرانه)؛ ذخیره HTML رندرشده در کش با `rendered=true`. اختیاری (`[render]`)؛ بدون playwright خطای واضح. تست با mock؛ smoke واقعی اگر chromium نصب شد.
5. `extract/markdown.py`: تولید Markdown مستقیم از نودها در همان پیمایش cleanhtml (حذف markdownify از مسیر اصلی؛ ZWNJ حفظ، جدول pipe، سلول چندخطی → HTML خام). تست برابری با خروجی قبلی روی fixtureها.
6. `pipeline`: ProcessPoolExecutor برای استخراج (یک پردازه به‌ازای هر هسته؛ `--workers`)، جدا از دریافت async؛ برای کمتر از ۴ صفحه inline. `fetch_and_extract` با صف و backpressure.
7. `cli crawl`: `--sitemap URL | --urls file`، `--concurrency`، `--limit`، `--only-changed` (مقایسه `content_hash` با `index.sqlite`)، `--ignore-robots`، `--render auto|never|always`، گزارش `run.json` کامل (n, ok, failed, rendered, skipped_unchanged, p50/p95 ms).
8. سنجش: `bench.speed` با ۸ پردازه؛ اجرای ۱۰ هزار URL (از کش، تکراری) بدون خطا؛ تست پایداری Playwright با `tools/playwright_stability_test.py` اگر chromium در دسترس بود؛ ثبت نتایج در BLUEPRINT (بخش تصمیم‌های باز).
9. در پایان: ruff/pytest سبز، `make bench` (F1 بدون افت)، CHANGELOG، تیک فاز ۴، DECISIONS.
