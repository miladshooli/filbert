# filbert

[![ci](https://github.com/miladshooli/filbert/actions/workflows/ci.yml/badge.svg)](https://github.com/miladshooli/filbert/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**استخراج سریع و دقیق محتوای اصلی و متادیتای SEO از صفحات وب، بهینه‌شده برای فارسی و زبان‌های راست‌به‌چپ.**

🇬🇧 [English README](README.md)

filbert یک URL (یا HTML خام) می‌گیرد و بدنهٔ اصلی صفحه را به‌صورت متن تمیز، HTML معنایی و Markdown برمی‌گرداند، به‌علاوهٔ هر چیزی که یک ممیزی SEO لازم دارد: زنجیرهٔ عنوان، description، canonical، robots، Open Graph، JSON-LD، نویسنده، تاریخ انتشار (با پشتیبانی تاریخ شمسی)، هدینگ‌ها، لینک‌ها، تصاویر، زبان، و چانک‌های آمادهٔ embedding. در مسیر اصلی هیچ LLMی نیست: سه استخراج‌گر قطعی روی هر بلوک رأی می‌دهند و کل خط لوله حدود ۱۵ میلی‌ثانیه برای هر صفحه طول می‌کشد.

## چرا یک استخراج‌گر دیگر؟

ابزارهای موجود (Trafilatura، Readability، newspaper) روی خبرهای انگلیسی تنظیم شده‌اند. سایت‌های فارسی مشکلات خودشان را دارند: نیم‌فاصله (ZWNJ) داخل کلمه‌ها، تفاوت حروف عربی و فارسی، تاریخ شمسی، نام کلاس‌های فینگلیش برای بخش‌های زائد (`nazarat`، `tabligh`، `matalebe-mortabet`) و فروشگاه‌های React/Nuxt فراوان. filbert روی یک بنچمارک ۲۰۰ صفحه‌ای فارسی با برچسب دستی ساخته شده که خبر، بلاگ، صفحهٔ محصول، لندینگ و انجمن را پوشش می‌دهد.

دو بنچمارک فارسی با برچسب انسانی، F1 متن اصلی در سطح توکن:

| دیتاست | صفحات | **filbert** | Trafilatura 2.3 | صفحات با F1 بالای ۰.۹ (filbert / Trafilatura) |
| --- | --- | --- | --- | --- |
| `fa-200`: خبر، بلاگ، محصول، لندینگ و انجمن از ۲۱ سایت | 202 | **0.861** | 0.728 | ۵۸٪ / ۳۳٪ |
| `fa-biz-100`: بلاگ ۴۵ کسب‌وکار ایرانی در ۱۳ حوزه | 84 | **0.956** | 0.839 | ۹۰٪ / ۴۴٪ |

| `fa-200` به تفکیک نوع | خبر | بلاگ | محصول | لندینگ | انجمن |
| --- | --- | --- | --- | --- | --- |
| filbert | 0.938 | 0.957 | 0.804 | 0.827 | 0.698 |
| Trafilatura | 0.842 | 0.909 | 0.706 | 0.503 | 0.511 |

روی `fa-biz-100` در همهٔ حوزه‌ها جلوتر است؛ از آموزش، منابع انسانی و رسانه (۰.۹۹ به بالا) تا فین‌تک و ابری (۰.۹۱ / ۰.۸۹). فیلدهای متادیتا (title، description، canonical، تاریخ انتشار، نویسنده) در ۱۰۰٪ صفحاتی که سایت آن‌ها را اعلام کرده با برچسب gold یکی است. گزارش کامل: [bench/report.md](bench/report.md).

## نصب

```bash
pip install "git+https://github.com/miladshooli/filbert"
# با امکانات اختیاری:
pip install "filbert[render,export,llm] @ git+https://github.com/miladshooli/filbert"
playwright install chromium   # فقط برای --render
```

امکانات اختیاری (extras): `server` (سرور HTTP API)، `render` (Playwright برای صفحات JS-محور)، `export` (Excel)، `llm` (استخراج schema-محور با SDK رسمی Anthropic)، `ml`، `lang`، `bench` (Trafilatura فقط به‌عنوان خط پایهٔ بنچمارک).

پایتون ۳.۱۲ به بالا؛ روی macOS، لینوکس و ویندوز کار می‌کند.

## شروع سریع

```bash
filbert extract https://nobitex.ir/mag/ --out out/ --formats json,html,md --json
filbert crawl --sitemap https://example.ir/sitemap.xml --limit 500 --only-changed --out out/
filbert chunk https://example.ir/post --max 250 --overlap 1 --out chunks.jsonl
filbert export out/<run-id> --xlsx seo.xlsx
filbert llm https://example.ir/post --schema seo          # نیاز به ANTHROPIC_API_KEY
```

```python
from filbert import extract_html

rec = extract_html(html, url="https://example.ir/post")
rec.seo.title, rec.seo.published_at, rec.seo.author      # متادیتا با فیلدهای *_source
rec.content.text, rec.content.markdown                   # متن نرمال‌شدهٔ فارسی / Markdown
rec.content.confidence, rec.content.blocks               # رأی هر بلوک از ensemble
rec.content.chunks[0].embed_text                         # «تیتر › مسیر هدینگ\n\nچانک»
rec.structure.links_summary, rec.structure.images_summary
rec.model_dump_json()                                    # همان JSON خط فرمان
```

دریافت async با کش، رندر مشروط و استخر پردازه:

```python
import asyncio
from filbert import fetch_and_extract
from filbert.config import Settings

stats, records = asyncio.run(fetch_and_extract(
    ["https://nobitex.ir/mag/", "https://www.zoomit.ir/"],
    settings=Settings(render="auto", workers=4),
    out_dir="out", formats=("json", "md"),
))
```

هر اجرا پوشهٔ `out/<run-id>/` را می‌سازد: `pages.jsonl` (هر خط یک `PageRecord`)، `chunks.jsonl`، `errors.jsonl`، `run.json` و فایل‌های جداگانهٔ `json/`، `html/`، `md/` برای هر صفحه.

## اجرا به‌صورت API

filbert را روی سرور بالا بیاورید و از هر زبانی صدا بزنید:

```bash
cp .env.example .env            # FILBERT_API_KEYS را پر کنید
docker compose up -d --build    # → http://localhost:8000/docs
# یا بدون Docker:
pip install "filbert[server,export] @ git+https://github.com/miladshooli/filbert"
FILBERT_API_KEYS=change-me filbert serve --host 0.0.0.0 --workers 4
```

```bash
curl -s localhost:8000/v1/extract -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.ir/post", "fields": ["seo", "content.text", "content.chunks"]}'
```

`POST /v1/extract` (یک URL یا HTML خام)، `POST /v1/extract/batch` (تا ۲۰ URL)، `POST /v1/jobs` (خزش پس‌زمینه از فهرست URL یا سایت‌مپ با خروجی NDJSON صفحه‌ها و چانک‌ها و گزارش Excel سئو) و `POST /v1/llm` اختیاری. کلید API، محافظ SSRF (آدرس‌های داخلی و متادیتای ابری را رد می‌کند، روی هر redirect هم)، سقف حجم و مستندات OpenAPI در `/docs` داخل خود سرور است. هر تگ نسخه، ایمیج `ghcr.io/miladshooli/filbert` را هم منتشر می‌کند. راهنمای کامل: [docs/API.md](docs/API.md).

## خروجی هر صفحه

```jsonc
{
  "url": "...", "final_url": "...", "canonical": "...", "fetched_at": "...",
  "http": { "status": 200, "response_ms": 412, "rendered": false, "from_cache": false, "detected_encoding": "utf-8" },
  "seo": {
    "title": "...", "title_source": "title_tag", "title_tag": "...", "og_title": "...", "h1": "...",
    "description": "...", "description_length": 136, "description_px_est": 876,
    "canonical": "...", "robots": { "raw": "index, follow", "noindex": false, "nofollow": false },
    "lang_declared": "fa", "lang_detected": "fa", "lang_scores": { "arabic_script": 0.99, "fa_vs_ar": 1.0 },
    "author": "...", "author_source": "json_ld",
    "published_at": "2026-11-01T12:26:30+00:00", "published_at_raw": "۱۰ آبان ۱۴۰۵", "published_at_source": "date_class",
    "open_graph": { "og:image": "https://..." }, "twitter": {}, "json_ld": [ ... ], "json_ld_types": ["NewsArticle"]
  },
  "content": {
    "text": "...", "text_raw": "...", "html": "<article lang=\"fa\" dir=\"rtl\">...</article>", "markdown": "# ...",
    "blocks": [{ "type": "p", "text": "...", "xpath": "/html/body/...", "votes": 3 }],
    "chunks": [{ "index": 0, "heading_path": ["..."], "text": "...", "embed_text": "...", "word_count": 180 }],
    "word_count": 1240, "reading_time_min": 6, "confidence": 0.94, "low_confidence": false,
    "extractors": { "readability": 1.0, "cetd": 0.97, "dom": 0.93 }
  },
  "structure": { "headings": [...], "links": [...], "images": [...], "links_summary": {...}, "images_summary": {...} },
  "content_hash": "a3f9...", "raw_html_ref": "cache/raw/<sha256>.html.zst"
}
```

## چطور کار می‌کند

```
دریافت (httpx، HTTP/2، محدودیت per-host، ETag/304، کش zstd)
  └─ heuristic «نیاز به JS» ──► رندر Playwright (اختیاری)
یک بار پارس (selectolax / lexbor)
  ├─ متادیتا از درخت کامل: head، JSON-LD، OG/Twitter، نویسنده، تاریخ‌ها، ساختار
  └─ preclean ──► بازنویسی Readability ─┐
                  CETD (چگالی متن) ─────┼─► رأی‌گیری بلوک‌سطح ──► HTML تمیز / Markdown / چانک
                  امتیاز ویژگی‌های DOM ──┘
```

- **لایهٔ دریافت:** async با connection pooling، همزمانی و فاصلهٔ per-host، retry نمایی روی 429/5xx/timeout، درخواست شرطی، HTML خام فشرده برای استخراج مجدد بدون شبکه، robots.txt، خزش sitemap، `--only-changed` با hash محتوا.
- **استخراج:** بازنویسی Readability موزیلا، چگالی متن ترکیبی (SIGIR 2011) و امتیازدهی ویژگی‌های DOM روی یک درخت اجرا می‌شوند و به هر بلوک رأی می‌دهند؛ بلوک با دو رأی یا بیشتر می‌ماند، با پر کردن حفره و fallback به حالت recall. اختلاف granularity ظرف/برگ حل می‌شود تا `ul` یک استخراج‌گر با `li`های استخراج‌گر دیگر هم‌خوان باشد.
- **فارسی:** نیم‌فاصله هرگز حذف نمی‌شود؛ حروف عربی و ارقام فقط در محتوا نرمال می‌شوند نه در متادیتا؛ الگوهای فینگلیش بخش‌های زائد در یک YAML قابل ویرایش هستند؛ شمارش کلمه نیم‌فاصله را مرز نمی‌داند؛ تاریخ شمسی به ISO تبدیل می‌شود؛ تشخیص زبان فارسی را از عربی جدا می‌کند.
- **چانکینگ:** چانک‌های ساختارآگاه از روی بلوک‌ها (سلسله‌مراتب هدینگ، برش فقط روی مرز جمله، جدول/کد/فهرست هیچ‌وقت وسط برش نمی‌خورند، هم‌پوشانی جمله‌ای، ادغام بخش‌های ریز) با `embed_text` که تیتر و مسیر هدینگ را دارد. طرح در [docs/CHUNKING.md](docs/CHUNKING.md).
- **خروجی برای پنل SEO:** ۱۵ قاعدهٔ ممیزی (طول و پهنای پیکسلی title/description، مشکلات h1، ناسازگاری canonical، noindex، alt گم‌شده، محتوای کم، ناسازگاری زبان…)، خروجی Excel با برگه‌های pages/issues/headings/links/images/chunks، و webhook امضاشده (`X-Filbert-Signature`، HMAC-SHA256).
- **لایهٔ اختیاری LLM:** `filbert llm` یک schema پایدانتیک (آمادهٔ `article` و `seo`، یا JSON Schema خودتان) را از Markdown تمیز با SDK رسمی Anthropic پر می‌کند، با prompt caching و کش دیسک. هیچ‌وقت در مسیر اصلی نیست.

## کارایی

روی بنچمارک ۲۰۲ صفحه‌ای، HTML کش‌شده، لپ‌تاپ Apple M-series (۴ هستهٔ پرقدرت + ۴ کم‌مصرف):

| | مقدار |
| --- | --- |
| p50 / p95 خط لوله برای هر صفحه | 16 / 51 میلی‌ثانیه |
| فقط ensemble استخراج، p50 | 9 میلی‌ثانیه |
| throughput با ۱ / ۴ / ۸ پردازه | 41 / 105 / 115 صفحه بر ثانیه |
| ۱۰٬۰۰۰ سند با ۸ پردازه | 177 صفحه بر ثانیه، صفر خطا |
| پیک حافظه روی بزرگ‌ترین صفحه (HTML ۱.۹ مگابایتی) | 15 مگابایت |

## تنظیمات

همهٔ تنظیمات در `filbert.config.Settings` (pydantic-settings) است و از `.env` یا متغیرهای `FILBERT_*` خوانده می‌شود: `FILBERT_CACHE_DIR`، `FILBERT_CONCURRENCY`، `FILBERT_RENDER=auto`، `FILBERT_WORKERS`، `FILBERT_WEBHOOK_URL`، `FILBERT_WEBHOOK_SECRET`، `FILBERT_CHUNK_MAX_WORDS`، `FILBERT_DIGITS=en`، `FILBERT_BOILERPLATE_PATH` (YAML الگوهای خودتان) و بیشتر. راهنمای کامل: [docs/USAGE.md](docs/USAGE.md).

## بنچمارک و توسعه

```bash
git clone https://github.com/miladshooli/filbert && cd filbert
uv sync --all-extras --group dev
uv run --all-extras pytest -q                 # ۲۶۸ تست
make bench                                    # همهٔ دیتاست‌ها در برابر Trafilatura، با gate رگرسیون
uv run --all-extras python -m bench.speed     # p50/p95 و throughput
```

دیتاست‌های `fa-200` (خبر، بلاگ، محصول، لندینگ و انجمن از ۲۱ سایت) و `fa-biz-100` (بلاگ ۴۵ کسب‌وکار در فین‌تک، بیمه، سفر، خرده‌فروشی، آموزش، سلامت، ابری و …) با برچسب gold بازبینی‌شدهٔ انسانی در `bench/datasets/` هستند. `bench/collect.py` آن را از `bench/sources.yml` دوباره می‌سازد؛ `bench/label.py` و ابزار بازبینی آنلاین برچسب gold می‌سازند؛ `bench/promote_labels.py` آن‌ها را اعمال می‌کند.

سند طراحی: [docs/BLUEPRINT.md](docs/BLUEPRINT.md). ثبت تصمیم‌ها: [docs/DECISIONS.md](docs/DECISIONS.md). تغییرات: [CHANGELOG.md](CHANGELOG.md).

## وضعیت و نقشهٔ راه

فازهای ۱ تا ۵ بلوپرینت پیاده‌سازی شده‌اند (هسته، ensemble، متادیتا، مقیاس، چانکینگ/خروجی‌ها/LLM). موارد باز: تست پایداری ۲ ساعتهٔ Playwright روی ویندوز، هدف ۳۰۰ صفحه بر ثانیه (فعلاً ۱۷۷ روی لپ‌تاپ)، و حالت اختیاری چانکینگ معنایی با embedding. Issue و Pull Request خوش‌آمدند، به‌ویژه الگوهای جدید بخش‌های زائد برای قالب‌های CMS فارسی و صفحات برچسب‌خوردهٔ بیشتر.

## مجوز

MIT © میلاد شولی
