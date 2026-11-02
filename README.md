# filbert

ابزار استخراج محتوای وب با دقت و سرعت بالا، بهینه برای فارسی.
طراحی کامل: [docs/BLUEPRINT.md](docs/BLUEPRINT.md) · راهنمای Claude Code: [CLAUDE.md](CLAUDE.md) · تصمیم‌ها: [docs/DECISIONS.md](docs/DECISIONS.md)

## شروع
```powershell
uv sync --all-extras
uv run pytest -q
uv run filbert extract https://nobitex.ir/mag/ --out out/ --formats json,html,md --json
uv run filbert extract page.html --out out/            # فایل محلی
```

## خزش و مقیاس
```
uv run filbert crawl --sitemap https://nobitex.ir/mag/sitemap.xml --limit 500 --only-changed --out out/
uv run filbert crawl --urls urls.txt --workers 8 --concurrency 32 --render auto     # رندر مشروط (uv sync --extra render; playwright install chromium)
uv run filbert extract https://www.digikala.com/ --render auto --ignore-robots      # فقط دامنه‌های خودتان
```
`--render auto` فقط صفحاتی را رندر می‌کند که heuristic «نیاز به JS» تشخیص دهد؛ `--only-changed` صفحات با `content_hash` یکسان را نمی‌نویسد؛ `robots.txt` پیش‌فرض رعایت می‌شود.

## چانک، Excel، webhook، LLM
```
uv run filbert chunk https://nobitex.ir/mag/<slug>/ --max 250 --overlap 1        # چانک‌های embedding-آماده (docs/CHUNKING.md)
uv run filbert export out/<run-id> --xlsx seo.xlsx                                # برگه‌های pages/issues/headings/links/images/chunks
uv run filbert crawl --urls urls.txt --webhook https://panel.example/hook           # POST دسته‌ای با امضای HMAC
uv run filbert llm https://... --schema seo                                       # نیاز به `uv sync --extra llm` و ANTHROPIC_API_KEY
```

## استفاده به‌عنوان کتابخانه
```python
from filbert import extract_html
rec = extract_html(html, url="https://...")   # بدون شبکه، همزمان
rec.seo.title, rec.content.markdown, rec.model_dump_json()
```

## خروجی
`out/<run-id>/` شامل `pages.jsonl`، `errors.jsonl`، `run.json` و پوشه‌های `json/`، `html/`، `md/` (یک فایل به‌ازای هر صفحه).
HTML خام در `cache/raw/<sha256>.html.zst` و ایندکس در `cache/index.sqlite` نگه داشته می‌شود؛ اجرای مجدد با ETag/304 بدون دانلود است.

## bench
```
make bench                                  # fa-200 + fixtures در برابر Trafilatura، با gate رگرسیون → bench/report.md
uv run python -m bench.collect --dataset fa-200     # جمع‌آوری/تکمیل دیتاست از bench/sources.yml
uv run python -m bench.label fa-200 --all           # صفحات برچسب‌زنی دستی → bench/datasets/fa-200/label/
uv run python -m bench.speed --dataset fa-200       # p50/p95 و throughput با ۱/۴/۸ پردازه
```
وضعیت فعلی در [bench/report.md](bench/report.md).

## توسعه
```
uv run ruff check . --fix && uv run ruff format .
uv run pytest -q
```
