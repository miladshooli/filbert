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

## استفاده به‌عنوان کتابخانه
```python
from filbert import extract_html
rec = extract_html(html, url="https://...")   # بدون شبکه، همزمان
rec.seo.title, rec.content.markdown, rec.model_dump_json()
```

## خروجی
`out/<run-id>/` شامل `pages.jsonl`، `errors.jsonl`، `run.json` و پوشه‌های `json/`، `html/`، `md/` (یک فایل به‌ازای هر صفحه).
HTML خام در `cache/raw/<sha256>.html.zst` و ایندکس در `cache/index.sqlite` نگه داشته می‌شود؛ اجرای مجدد با ETag/304 بدون دانلود است.

## توسعه
```
uv run ruff check . --fix && uv run ruff format .
uv run pytest -q
```
