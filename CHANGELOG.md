# Changelog

## [0.2.0] — 2026-11-01 — فاز ۲: ensemble و bench

- `extract/blocks.py`: `RawBlock` مشترک سه استخراج‌گر (کلید XPath+hash، ترتیب سند، منطق تولید بلوک).
- `extract/cetd.py`: چگالی متن ترکیبی (SIGIR 2011) در یک پیمایش معکوس پیش‌ترتیب.
- `extract/domscore.py`: ویژگی‌های DOM با وزن ثابت + هموارسازی همسایه + ویژگی «گروه تکرارشونده» (پست انجمن/آیتم).
- `extract/ensemble.py`: رأی‌گیری با آگاهی از دربرگیری، حذف ظرف بر اساس پوشش، پر کردن حفره، لنگر CETD برای صفحات فهرستی، fallback recall، `confidence` و سهم استخراج‌گرها؛ `--recall` در CLI.
- `preclean`: ظرف مخفی بزرگ (streaming SSR ری‌اکت `<div hidden id="S:0">`) حذف نمی‌شود؛ الگوهای تبلیغ (`native-ad`, `-ad-`, `sponsored`, …).
- `bench/`: ارزیابی توکن‌سطح (P/R/F1، دقت صفحه، متادیتا)، خط پایه Trafilatura، `report.md`، gate رگرسیون (`make bench`)، سنجش سرعت (`bench.speed`)، آزمایش fusion (`bench.experiments`).
- دیتاست `fa-200`: ۲۰۰ صفحه فارسی از ۲۲ سایت (۶۰ خبر، ۴۱ بلاگ، ۴۰ محصول، ۳۰ لندینگ، ۳۱ انجمن)، ۱۸۸ برچسب `auto` با selector مخصوص سایت؛ ابزار جمع‌آوری (`bench.collect`) و برچسب‌زنی (`bench.label`). دیتاست `fixtures` با gold دستی.
- نتیجه روی fa-200 (برچسب auto): ensemble F1 **0.807** در برابر Trafilatura **0.798** (+0.9)؛ p50 10.98ms در برابر 19.9ms. به تفکیک: خبر 0.875/0.849، بلاگ 0.921/0.878، لندینگ 0.866/0.753، انجمن 0.604/0.581، محصول 0.695/0.826. معیار خروج فاز (+۳ امتیاز) هنوز **برآورده نشده**؛ شکاف اصلی صفحات محصول و کیفیت برچسب‌های auto است.
- سرعت (ماشین توسعه، 202 صفحه، میانه 196KB): pipeline p50 15.01ms / p95 51.18ms؛ throughput 42.0 / 111.5 / 125.4 صفحه بر ثانیه با ۱/۴/۸ پردازه؛ پیک حافظه بزرگ‌ترین صفحه 14.7MB.

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
