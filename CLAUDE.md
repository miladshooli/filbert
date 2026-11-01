# filbert — راهنمای پروژه برای Claude Code

## این پروژه چیست
ابزار استخراج محتوای وب (main content + متادیتای SEO) با تمرکز بر **دقت** و **سرعت**، بهینه برای فارسی/RTL و زبان‌های دیگر.
سند کامل طراحی: `docs/BLUEPRINT.md` — **قبل از هر کار آن را بخوان**. هر تصمیمی که با آن تضاد دارد باید اول در همان سند ثبت شود.

## قواعد غیرقابل‌مذاکره
- **هیچ LLM در مسیر اصلی استخراج.** فقط الگوریتم‌های قطعی (Readability بازنویسی‌شده، CETD، امتیاز ویژگی DOM).
- **فقط یک پارس HTML با `selectolax`.** `lxml`، `BeautifulSoup`، `html5lib` ممنوع (به‌جز داخل `bench/` برای ابزارهای خط پایه).
- **Trafilatura فقط در extras `[bench]`**؛ هرگز در `src/` import نشود.
- **ZWNJ (`U+200C`) هرگز حذف نمی‌شود.** هر تابع نرمال‌سازی باید با `hypothesis` تست شود که ZWNJ معتبر را نگه می‌دارد.
- JSON با `orjson` و بدون escape یونیکد (`OPT_NON_STR_KEYS` نه؛ پیش‌فرض کافی است).
- نسخه خام هر متن (`text_raw`) در کنار نسخه نرمال‌شده ذخیره می‌شود؛ متادیتا هرگز نرمال‌سازی فارسی نمی‌شود.
- هر ماژول جدید = تست جدید در `tests/`. PR بدون تست merge نمی‌شود.
- هر تغییر در `src/filbert/extract/` باید `make bench` را اجرا کند؛ افت بیش از 0.5 F1 یا ۱۰٪ سرعت قابل قبول نیست.

## استک
Python 3.12 · uv · pydantic v2 · httpx[http2] · selectolax · orjson · markdownify · typer · rich · pytest · hypothesis · ruff
اختیاری: `[render]` playwright · `[ml]` lightgbm · `[bench]` trafilatura

## دستورات
```
uv sync --all-extras          # نصب
uv run pytest -q              # تست
uv run ruff check . --fix     # لینت
uv run filbert extract <url|file> --out out/ --formats json,html,md
uv run filbert bench --dataset fa-200
```

## محیط توسعه
ویندوز + PowerShell + VS Code. مسیرها را با `pathlib` بساز؛ فایل‌ها را همیشه با `encoding="utf-8"` باز کن؛ نام فایل خروجی باید ویندوز‌سازگار باشد (بدون `: ? * < > | "`).
شبکه پشت VPN است: timeout‌ها سخاوتمندانه و retry با backoff.

## سبک کد
- type hints کامل، docstring کوتاه فارسی یا انگلیسی (یکدست در هر ماژول).
- توابع خالص برای استخراج؛ I/O فقط در `fetch/` و `out/`.
- لاگ با `logging`، نه `print`. سطح پیش‌فرض WARNING.
- هیچ global state؛ تنظیمات از `config.py` (pydantic-settings) تزریق می‌شود.

## وضعیت فازها
- [ ] فاز ۱ — هسته (مدل داده، fetch+کش، preclean، Readability، سه نویسنده، CLI)
- [ ] فاز ۲ — ensemble (CETD، DOM-scorer، رأی‌گیری، fa-200، bench)
- [ ] فاز ۳ — متادیتای کامل + فارسی
- [ ] فاز ۴ — رندر مشروط + مقیاس
- [ ] فاز ۵ — هوش اختیاری (lightgbm، CRF، --llm)
وقتی فازی تمام شد، همین فهرست را تیک بزن و خلاصه تغییرات را در `CHANGELOG.md` بنویس.
