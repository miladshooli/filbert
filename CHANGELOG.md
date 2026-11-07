# Changelog

## [0.5.2] — 2026-11-07 — بنچمارک بلاگ کسب‌وکارها

- دیتاست **fa-biz-100**: ۸۵ مقاله از بلاگ ۴۵ کسب‌وکار ایرانی در ۱۳ حوزه، بازبینی انسانی در ابزار آنلاین (۷۷ gold، ۷ نامطمئن، ۱ رد). نتیجه: **filbert 0.956 در برابر Trafilatura 0.839**؛ ۹۰٪ صفحات F1 بالای ۰.۹ (Trafilatura ۴۴٪).
- اصلاح preclean: بخش نظرات وردپرس که هر نظر را در `<article class="comment-body">` می‌گذارد دیگر به‌خاطر محافظ «ظرفِ article» حفظ نمی‌شود (کلاس‌های taxonomy مثل `tag-…` نادیده گرفته می‌شوند تا پست واقعی محافظت بماند). fidibo از 0.67 به 0.99 رسید.
- ensemble: هدینگ تک‌رأی بین بلوک‌های قطعی (فاصله ≤ ۲) پذیرفته می‌شود (تیترهای بخش در لندینگ‌های React).
- عبارت‌های UI با دونقطهٔ انتهایی («فهرست:»، «دسته بندی ها:») و برچسب‌های «برچسب‌ها/تگ‌ها» حذف می‌شوند.
- ابزار: `bench.review_export` (دادهٔ ابزار بازبینی از هر دیتاست، با پیش‌تیک silver از خروجی filbert برای صفحات بدون برچسب خودکار)، کشف URL با پیمایش دسته‌ها (depth 2)، `bench.collect --sources-file`.

## [0.5.1] — 2026-11-03 — برچسب‌های انسانی fa-200

- ۲۰۲ صفحه fa-200 با ابزار بازبینی آنلاین (Artifact با پایگاه داده) دستی بازبینی شد: ۲۰۰ gold، ۲ نامطمئن، ۰ رد. برچسب‌های خام در `bench/datasets/fa-200/labels/`؛ `bench.promote_labels` آن‌ها را به `gold/` تبدیل می‌کند. برچسب انسانی با خودکار به‌طور میانگین F1=0.837 هم‌پوشانی داشت؛ ۵۶ صفحه تفاوت بزرگ داشتند.
- **نتیجه روی gold انسانی (۲۰۲ صفحه): ensemble F1 = 0.862 در برابر Trafilatura 0.728 (+13.4)**. به تفکیک: خبر 0.938/0.842، بلاگ 0.957/0.909، محصول 0.804/0.706، لندینگ 0.827/0.503، انجمن 0.698/0.511. دقت صفحه (F1 > 0.9): 58٪ در برابر 33٪. متادیتا (title/description/canonical/published_at/author) 100٪.
- مدل یادگیرنده DOM روی gold انسانی با CV به تفکیک سایت از وزن‌های دستی **بدتر** شد (0.855 در برابر 0.866)؛ فایل مدل حذف شد و `--dom-model` فقط برای آزمایش می‌ماند.
- `filbert llm` با کلید واقعی آزمایش شد (article + seo روی یک خبر نوبیتکس): JSON معتبر، بدون توهم، ~۳ سنت برای هر فراخوانی.
- `Makefile` با `uv run --all-extras` (اجرای `uv run` بدون extras محیط را به حالت بدون trafilatura/numpy برمی‌گرداند).

## [0.5.0] — 2026-11-02 — فاز ۵: چانکینگ، خروجی‌های پنل، هوش اختیاری

- **چانکینگ فارسی‌بهینه** (`filbert.chunk`، طرح در `docs/CHUNKING.md`): جداکننده جمله ZWNJ-امن (اعشار، URL، اختصار، نقل‌قول)، چانکر ساختاری روی بلوک‌ها (مرز سخت تا H3 مؤثر، بودجه ۲۵۰ کلمه/سقف ۴۰۰، هم‌پوشانی یک جمله، جدول/فهرست/کد اتمی با تقسیم امن، ادغام بخش‌های ریز)، `embed_text` با پیشوند «تیتر › مسیر هدینگ»، `content.chunks` در JSON، `chunks.jsonl` در هر run، دستور `filbert chunk`. روی fa-200: ۱۳۳۸ چانک، p10/p50/p90 = 53/143/247 کلمه، صفر چانک بالای سقف، صفر ZWNJ لبه‌ای (`bench.chunk_report`).
- **خروجی‌های پنل:** `out/issues.py` (۱۵ قاعده ممیزی SEO: title/description طول و پیکسل، h1 گم‌شده/چندتایی، canonical، noindex، alt، محتوای کم، زبان ناسازگار، بدون JSON-LD)، `filbert export --xlsx` (برگه‌های pages/issues/headings/links/images/chunks، راست‌چین، فیلتر و freeze)، `--webhook URL` با دسته‌بندی، retry نمایی و امضای HMAC-SHA256 (`FILBERT_WEBHOOK_SECRET`).
- **DOM-scorer یادگیرنده** (`bench.train_dom`، extras `[ml]`): آموزش روی برچسب‌های fa-200 با CV به تفکیک سایت؛ lightgbm یا fallback sklearn؛ `--dom-model data/models/dom_lgbm.pkl`. نتیجه CV end-to-end: ensemble 0.8435 → 0.8485 (+0.5، ۲ از ۵ fold بدتر) → **پیش‌فرض خاموش** تا بازبینی gold.
- **لایه LLM اختیاری** (`filbert llm`، extras `[llm]`، SDK رسمی anthropic): استخراج schema-محور از Markdown تمیز با `messages.parse`، schemaهای آماده `article`/`seo` یا JSON Schema دلخواه، prompt caching روی system، کش پاسخ روی دیسک، مدل پیش‌فرض `claude-opus-5-5`؛ خارج از مسیر اصلی. (بدون کلید API در این محیط فقط با client ساختگی تست شده.)

## [0.4.0] — 2026-11-02 — فاز ۴: رندر مشروط و مقیاس

- `fetch/needs_js.py`: heuristic «نیاز به JS» (متن قابل‌مشاهده/حجم HTML، پوسته خالی `#root/#app/#__next/#__nuxt`، نسبت script، دامنه‌های همیشه‌رندر).
- `fetch/render.py`: استخر Playwright (اختیاری `[render]`): ۲–۴ context، بلاک تصویر/فونت/مدیا/استایل، سقف networkidle، ری‌استارت پیشگیرانه و بازیابی کرش. `--render auto|always`؛ HTML رندرشده در کش با `rendered=1`. آزمایش واقعی: دیجی‌کالا و اُکالا تشخیص و رندر شدند (دیجی‌کالا ۰ → ۳۴۰ کلمه).
- `fetch/robots.py`: robots.txt یک بار در هر دامنه، کش ۲۴ساعته حافظه+دیسک، `--ignore-robots`.
- `fetch/sitemap.py` + `filbert crawl --sitemap|--urls --limit --pattern --exclude --concurrency --only-changed --workers --render`.
- `pipeline`: استخراج در ProcessPool (≥۴ URL)، `--only-changed` با `content_hash` در `index.sqlite`، شمارنده‌های `rendered/skipped_unchanged/robots_blocked` در `run.json`؛ run-id یکتا در یک ثانیه؛ upsert کش `content_hash` را نگه می‌دارد.
- `extract/markdown.py`: Markdown مستقیم از نودها (markdownify فقط fallback).
- `extract/blocks.PageContext`: آمار نود و کش بلوک مشترک بین سه استخراج‌گر؛ چگالی لینک یکدست → **F1 ensemble روی fa-200: 0.840 در برابر Trafilatura 0.798 (+4.2؛ معیار خروج فاز ۲ برآورده شد)**.
- `bench/scale.py`: ۱۰٬۰۰۰ سند از کش با ۸ پردازه: **177 صفحه/ثانیه**، صفر خطا (392 صفحه خالی = پوسته‌های JS). `bench.speed`: pipeline p50 18ms / p95 54ms؛ 41 / 105 / 115 صفحه بر ثانیه با ۱/۴/۸ پردازه؛ پیک حافظه 15MB. **هدف ۳۰۰ صفحه/ثانیه برآورده نشد** (ماشین ۴+۴ هسته؛ مقیاس‌پذیری ۳×).
- تست پایداری Playwright (۴ دقیقه، ۳ context، VPN): موفقیت ۹۶.۴٪، ۰ کرش — `docs/stability-2026-11-02.md`؛ تست ۲ ساعته ویندوز باقی است.

## [0.3.0] — 2026-11-02 — فاز ۳: متادیتای کامل + فارسی

- `meta/jsonld.py`: پارس tolerant همه JSON-LDها (آرایه، `@graph`، CDATA، ویرگول اضافه، JSON خراب)، `json_ld_types`، نویسنده/تاریخ/کلیدواژه از JSON-LD.
- `meta/dates.py`: ISO 8601/RFC 2822، تاریخ شمسی (`۱۴۰۵/۰۸/۱۰`، `۱۰ آبان ۱۴۰۵`) و میلادی (فارسی/انگلیسی) در متن، تبدیل با jdatetime، `published_at_raw` با ارقام اصلی؛ تست hypothesis round-trip شمسی.
- `meta/social.py`: OG/Twitter با URL مطلق؛ زنجیره نویسنده `meta[name=author]` → JSON-LD → `rel=author` → لینک `/author/` → class/byline، با حذف پیشوند و تاریخ.
- `meta/structure.py`: هدینگ‌ها/لینک‌ها/تصاویر از درخت کامل پیش از preclean؛ `in_main` با عضویت نود در بلوک‌های برنده؛ خلاصه‌ها.
- `meta/enrich.py`: زنجیره تاریخ `article:published_time` → JSON-LD → `<time datetime>` → `meta[name=date]` → عناصر با class تاریخ → regex در ابتدای متن اصلی؛ `modified_at`؛ طول و پهنای پیکسلی تقریبی description؛ تشخیص زبان.
- `fa/lang.py`: `fa`/`ar`/`en`/`mixed` با نسبت خط و حروف اختصاصی + کلمات پربسامد؛ lingua اختیاری (`[lang]`) فقط برای موارد مبهم.
- `models`: `author_source`, `published_at_source`, `modified_at_raw`, `lang_scores`, `title_length`, `description_length`, `description_px_est`.
- bench: gold متادیتای نیمه‌خودکار (`bench.meta_gold`؛ published_at/author از داده ساخت‌یافته خود سایت) و خط پوشش متادیتا در گزارش. دقت فیلدی روی fa-200: title/description/canonical/published_at/author = 1.0 (gold نیمه‌خودکار؛ بازبینی دستی لازم).
- کارایی: کش و مسیر سریع `normalize_url`، ساخت مدل‌های ساختار فقط یک بار. pipeline p50 روی fa-200: 19.5ms (پیش از فاز ۳: 15.8ms؛ هزینه جمع‌آوری لینک/تصویر/هدینگ و JSON-LD).

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
