# راهنمای استفاده از filbert

## نصب
```
# در پروژه خودتان (uv یا pip)؛ ریپو پرایوت است، پس با دسترسی گیت‌هاب:
uv add "filbert @ git+https://github.com/miladshooli/filbert"
pip install "git+https://github.com/miladshooli/filbert"

# با امکانات اختیاری:
pip install "filbert[render,export,llm] @ git+https://github.com/miladshooli/filbert"
playwright install chromium          # فقط اگر render می‌خواهید

# یا از wheel:  uv build  →  dist/filbert-0.5.1-py3-none-any.whl
```
extras: `render` (Playwright)، `export` (Excel)، `llm` (SDK anthropic)، `ml` (مدل‌های یادگیرنده)، `lang` (lingua)، `bench` (Trafilatura، فقط برای مقایسه).

## خط فرمان
```
filbert extract <url|file>... --out out/ --formats json,html,md [--json] [--render auto] [--only-changed]
filbert crawl --sitemap https://site.ir/sitemap.xml --limit 2000 --concurrency 32 --only-changed --out out/
filbert crawl --urls urls.txt --workers 8 --webhook https://panel.example/hook
filbert chunk <url|file> --max 250 --overlap 1 --out chunks.jsonl
filbert export out/<run-id> --xlsx seo.xlsx
filbert llm <url|file> --schema article|seo|schema.json      # نیاز به ANTHROPIC_API_KEY
filbert bench --dataset fa-200 --compare-with trafilatura     # فقط در ریشه مخزن
```
خروجی هر اجرا در `out/<run-id>/`: `pages.jsonl` (یک خط = یک `PageRecord`)، `chunks.jsonl`، `errors.jsonl`، `run.json`، و پوشه‌های `json/`، `html/`، `md/`.
کش در `cache/` (HTML خام zstd + `index.sqlite`): اجرای مجدد با ETag/304 بدون دانلود، و `--only-changed` صفحات بدون تغییر را نمی‌نویسد.

## کتابخانه
```python
from filbert import extract_html            # بدون شبکه، همزمان
rec = extract_html(html, url="https://...")
rec.seo.title, rec.seo.published_at, rec.seo.author
rec.content.text, rec.content.markdown, rec.content.confidence
rec.content.chunks[0].embed_text             # برای embedding
rec.structure.links_summary, rec.structure.images_summary
rec.model_dump_json()                        # همان JSON خط فرمان

import asyncio
from filbert import fetch_and_extract        # async: دریافت + استخراج + ذخیره
from filbert.config import Settings
stats, records = asyncio.run(fetch_and_extract(
    ["https://nobitex.ir/mag/"], settings=Settings(render="auto", workers=4), out_dir="out", formats=("json",)
))

from filbert.chunk import chunk_blocks, ChunkOptions
chunks = chunk_blocks(rec.content.blocks, opts=ChunkOptions(max_units=300), title=rec.seo.title)

from filbert.out.issues import find_issues  # قواعد ممیزی SEO
from filbert.out.excel import export_xlsx
from filbert.llm import LLMExtractor, SeoBrief
brief = LLMExtractor().extract(rec.content.markdown, SeoBrief, url=rec.url)
```

## تنظیمات
همه گزینه‌ها در `filbert.config.Settings` (pydantic-settings): از `.env` یا متغیرهای `FILBERT_*` خوانده می‌شوند، مثلاً
`FILBERT_CACHE_DIR`, `FILBERT_CONCURRENCY`, `FILBERT_RENDER=auto`, `FILBERT_WEBHOOK_URL`, `FILBERT_WEBHOOK_SECRET`,
`FILBERT_CHUNK_MAX_WORDS`, `FILBERT_DIGITS=en`, `FILBERT_BOILERPLATE_PATH` (YAML الگوهای boilerplate خودتان).

## اتصال به پنل SEO
- **push:** `--webhook URL` → POST دسته‌ای `{run_id, count, records[]}` با هدر `X-Filbert-Signature: sha256=<HMAC>` (کلید `FILBERT_WEBHOOK_SECRET`). رکوردها همان `PageRecord` هستند.
- **pull:** `pages.jsonl` را با pandas/duckdb بخوانید؛ یا `filbert export --xlsx`.
- **تشخیص تغییر:** `content_hash` در هر رکورد و در `cache/index.sqlite`؛ `--only-changed` برای خزش‌های دوره‌ای.
- **RAG:** `chunks.jsonl` → فیلد `embed_text` را embed کنید؛ `heading_path`, `xpath_start`, `position` برای ارجاع.

## نکات عملی
- پشت VPN همزمانی را بالا نبرید؛ پیش‌فرض ۴ درخواست همزمان و ۲۵۰ms فاصله به‌ازای هر دامنه.
- `robots.txt` رعایت می‌شود؛ `--ignore-robots` فقط برای دامنه‌های خودتان.
- صفحات JS-رندر با `--render auto` تشخیص و رندر می‌شوند (نیاز به extras `render`).
- ویندوز: مسیرها و نام فایل‌ها سازگارند؛ `uv run filbert ...` در PowerShell همان‌طور کار می‌کند.
