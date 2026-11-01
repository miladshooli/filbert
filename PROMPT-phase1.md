docs/BLUEPRINT.md و CLAUDE.md را کامل بخوان. سپس **فاز ۱** را پیاده‌سازی کن. قبل از نوشتن کد، یک plan کوتاه (حداکثر ۱۵ خط) بده و بعد شروع کن.

مراحل:
1. `pyproject.toml` با uv، python>=3.12، ruff، pytest، hypothesis، pytest-httpserver؛ extras: `render` (playwright)، `ml` (lightgbm)، `bench` (trafilatura). ساختار پوشه‌ها دقیقاً مطابق بخش «ساختار پروژه» در BLUEPRINT.
2. `src/filbert/models.py`: `PageRecord` و زیرمدل‌ها با pydantic v2 از روی JSON نمونه بخش «فرمت‌های خروجی». `schema_version="1.0"`. هر فیلد غایب `None`، نه رشته خالی.
3. `fetch/urlnorm.py`: نرمال‌سازی URL (حذف utm_*/fbclid/gclid/yclid/ref، مرتب‌سازی query، حذف fragment، lowercase host) + تشخیص داخلی/خارجی با eTLD+1. تست.
4. `fetch/client.py` + `fetch/cache.py`: httpx AsyncClient با HTTP/2، per-host semaphore (۴ همزمان، ۲۵۰ms فاصله)، retry نمایی روی 429/5xx/timeout، ETag/If-None-Match و 304، ذخیره HTML خام با zstd (کلید sha256 آدرس نرمال‌شده)، ایندکس SQLite با WAL. تست با pytest-httpserver برای: 200، 304، redirect، 429→retry، timeout، encoding windows-1256.
5. `extract/preclean.py` + `data/boilerplate_fa.yml`: حذف تگ‌ها و الگوهای class/id بخش «گام ۰» (شامل الگوهای فینگلیش). استثنای `header`/`h1` داخل `article|main`. تست مثبت/منفی برای هر قانون.
6. `extract/readability.py`: بازنویسی الگوریتم Readability روی selectolax طبق «گام ۱» → `list[Block(type, text, html, xpath)]`. وزن class/id از YAML. ۵ fixture HTML فارسی در `tests/fixtures/` (خبر، بلاگ، محصول، لندینگ، انجمن) با متن مورد انتظار.
7. `extract/cleanhtml.py`: ساخت HTML معنایی تمیز از بلوک‌ها (فقط تگ‌های مجاز، فقط attribute‌های مجاز، `lang="fa" dir="rtl"`).
8. `fa/normalize.py` و `fa/tokenize.py`: نرمال‌سازی حروف/ارقام/کاراکترهای ناپیدا طبق بخش «ملاحظات فارسی»؛ شمارش کلمه با ZWNJ به‌عنوان غیرمرز. تست hypothesis: idempotent و حفظ ZWNJ.
9. `meta/head.py` (فقط title/description/keywords/canonical/robots/lang با زنجیره اولویت و `*_source`) — بقیه متادیتا فاز ۳.
10. `out/json_writer.py`, `out/html_writer.py`, `out/md_writer.py`, `out/store.py`: سه خروجی + layout دیسک + `pages.jsonl` + `run.json`.
11. `pipeline.py` و `cli.py` (typer): `filbert extract <url|file> [--out] [--formats json,html,md]` با progress از rich.
12. در پایان: `uv run ruff check .` بدون خطا، `uv run pytest -q` سبز، و یک اجرای واقعی روی این سه URL با نمایش خلاصه JSON:
    - https://nobitex.ir/blog/
    - https://www.zoomit.ir/
    - https://fa.wikipedia.org/wiki/تهران

قواعد: به CLAUDE.md پایبند باش. هر مرحله را commit جداگانه کن (پیام انگلیسی، conventional commits). اگر جایی BLUEPRINT مبهم بود، ساده‌ترین تفسیر را انتخاب کن و در `docs/DECISIONS.md` یک خط بنویس.
