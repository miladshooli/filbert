# Changelog

## [0.1.0] — 2026-11-01 — فاز ۱: هسته

- `pyproject.toml` با uv، Python ≥3.12، ruff، pytest، hypothesis، pytest-httpserver؛ extras `render`/`ml`/`bench`.
- `models.py`: `PageRecord` و زیرمدل‌ها (pydantic v2، `schema_version="1.0"`، غایب = `null`).
- `fetch/urlnorm.py`: حذف پارامترهای ردیابی، مرتب‌سازی query، حذف fragment، lowercase host، percent-encoding یکدست، eTLD+1 آفلاین.
- `fetch/client.py` + `fetch/cache.py`: httpx AsyncClient (HTTP/2)، محدودیت per-host (۴ همزمان، ۲۵۰ms)، retry نمایی روی 429/5xx/timeout، ETag/If-None-Match و 304 از کش، HTML خام zstd با کلید sha256، ایندکس SQLite WAL، تشخیص encoding (هدر → meta → charset-normalizer).
- `extract/preclean.py` + `boilerplate_fa.yml`: حذف تگ‌ها/مخفی‌ها/کامنت‌ها و الگوهای class/id انگلیسی + فینگلیش؛ استثنای `header`/`h1` داخل `article|main`.
- `extract/readability.py`: بازنویسی Readability روی selectolax (lexbor) با وزن class/id از YAML، انتخاب خواهر/برادر، تشخیص سطح چندبخشی، خروجی `Block(type,text,html,xpath)`؛ ۵ fixture فارسی (خبر، بلاگ، محصول، لندینگ، انجمن).
- `extract/cleanhtml.py`: HTML معنایی تمیز مستقیم از نودها (بدون پارس دوم)، URL مطلق، `dir="auto"`.
- `fa/normalize.py` + `fa/tokenize.py`: نرمال‌سازی حروف/ارقام/ناپیداها، حفظ ZWNJ (تست hypothesis: idempotent + حفظ ZWNJ معتبر)، شمارش کلمه با ZWNJ غیرمرز.
- `meta/head.py`: title/description/keywords/canonical/robots/hreflang/lang با زنجیره اولویت و `*_source`؛ OG/Twitter خام.
- `out/`: JSON (orjson، بدون escape یونیکد)، HTML (پوسته حداقلی)، Markdown (front-matter + بدنه)، `Store` با layout `out/<run-id>/…`، `pages.jsonl`، `errors.jsonl`، `run.json`، slug ویندوزسازگار.
- `pipeline.py` + `cli.py`: `filbert extract <url|file>... --out --formats --json --force`.
- ۱۳۶ تست سبز؛ ruff بدون خطا. سرعت استخراج (بدون شبکه، یک هسته M-series): ۱۹۳KB → ~۴ms، ۱MB → ~۳۰ms، ۱.۹MB (۳۰۰ بلوک) → ~۲۲۵ms.
