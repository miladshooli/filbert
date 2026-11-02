فاز ۵ — هوش اختیاری + خروجی‌های پنل + چانکینگ فارسی. هیچ‌کدام در مسیر اصلی استخراج قرار نمی‌گیرند (قاعده CLAUDE.md).

مراحل:
1. `chunk/`: چانکینگ ساختارآگاه و فارسی‌بهینه (طرح در `docs/CHUNKING.md`؛ پس از تأیید): جداکننده جمله فارسی (ZWNJ-امن)، چانک بر پایه سلسله‌مراتب هدینگ، جدول/کد تقسیم نمی‌شود، هم‌پوشانی جمله‌ای، شمارنده اندازه قابل تعویض (کلمه/کاراکتر/tiktoken)، متادیتای هر چانک (مسیر هدینگ، XPath، موقعیت). `content.chunks` در JSON + `chunks.jsonl` + `filbert chunk`. تست + معیارهای کیفیت مرز.
2. `out/excel.py` (`[export]` با openpyxl): `filbert export --xlsx` از `pages.jsonl` با `utf-8-sig`، ستون‌های فارسی راست‌چین، برگه‌های pages/headings/links/images/issues (SEO issues: بدون description، h1 چندتایی، alt گم‌شده، canonical ناسازگار، description بلند/کوتاه).
3. `out/webhook.py`: POST هر `PageRecord` (یا دسته‌ای) به URL با retry/backoff و امضای HMAC اختیاری؛ `filbert crawl --webhook URL`.
4. `extract/domscore` با lightgbm (`[ml]`): `bench/train_dom.py` ویژگی‌های موجود → مدل روی برچسب‌های gold/auto fa-200 (cross-validation به تفکیک سایت)؛ مدل فقط اگر F1 ensemble را بالا ببرد جایگزین وزن‌های دستی شود؛ فایل مدل در `data/models/`.
5. نویسنده با قواعد دقیق‌تر + مدل سبک (CRF یا lightgbm روی کاندیدهای byline) فقط اگر داده کافی باشد؛ وگرنه قواعد.
6. لایه `--llm` (`[llm]`): استخراج ساختاریافته با schema (pydantic) از Markdown تمیز، الگوی lightfeed؛ provider قابل تعویض؛ خارج از مسیر اصلی؛ کش پاسخ.
7. bench: F1 بدون افت، سرعت مسیر اصلی بدون افت، گزارش chunking.
