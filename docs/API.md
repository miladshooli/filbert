# سرور API filbert

filbert را می‌شود روی هر سروری به‌صورت یک سرویس HTTP بالا آورد تا پنل SEO، سیستم RAG یا هر برنامهٔ دیگری (به هر زبانی) بدون نصب پایتون از آن استفاده کند. سرور همان pipeline کتابخانه است و خروجی‌اش همان `PageRecord` خط فرمان است؛ فقط یک لایهٔ FastAPI رویش نشسته.

- مستندات تعاملی (Swagger) روی خود سرور: `/docs`؛ نسخهٔ ReDoc: `/redoc`؛ اسکیمای OpenAPI: `/openapi.json`.
- extras لازم: `server` (FastAPI و uvicorn) و برای خروجی Excel، `export`. برای رندر JS، `render`.

## راه‌اندازی

### با Docker (پیشنهادی)

```bash
git clone https://github.com/miladshooli/filbert && cd filbert
cp .env.example .env
# در .env یک کلید بگذارید:
#   FILBERT_API_KEYS=<خروجی: python -c "import secrets; print(secrets.token_urlsafe(32))">
docker compose up -d --build
curl http://localhost:8000/health
```

کش HTML و خروجی jobها در volume `filbert-data` (مسیر `/data` داخل کانتینر) می‌ماند و با ری‌استارت پاک نمی‌شود.

بعد از هر تگ نسخه (`vX.Y.Z`)، ایمیج آماده در GitHub Container Registry منتشر می‌شود و بدون clone هم می‌شود اجرا کرد:

```bash
docker run -d --name filbert -p 8000:8000 \
  -e FILBERT_API_KEYS=change-me -e FILBERT_SERVE_WORKERS=2 \
  -v filbert-data:/data --restart unless-stopped \
  ghcr.io/miladshooli/filbert:latest
```

صفحه‌های JS-محور (React/Nuxt بدون SSR) به Chromium نیاز دارند. ایمیج رندر را جدا بسازید (حدود ۱.۵ گیگابایت) و `FILBERT_RENDER=auto` بگذارید:

```bash
docker build --build-arg WITH_RENDER=1 -t filbert:render .
```

### بدون Docker

```bash
pip install "filbert[server,export] @ git+https://github.com/miladshooli/filbert"
export FILBERT_API_KEYS=change-me
filbert serve --host 0.0.0.0 --port 8000 --workers 4
```

`filbert serve` تنظیماتش را از متغیرهای `FILBERT_*` و فایل `.env` در پوشهٔ جاری می‌خواند. میزبان، پورت و تعداد پردازه را با `FILBERT_SERVE_HOST`، `FILBERT_SERVE_PORT` (یا `PORT` برای سرویس‌هایی مثل Render و Railway) و `FILBERT_SERVE_WORKERS` هم می‌شود داد. اگر `FILBERT_API_KEYS` خالی باشد و سرور روی آدرسی غیر از localhost گوش کند، هشدار می‌دهد.

نمونهٔ سرویس systemd:

```ini
[Service]
WorkingDirectory=/srv/filbert
EnvironmentFile=/srv/filbert/.env
ExecStart=/srv/filbert/.venv/bin/filbert serve --host 127.0.0.1 --port 8000 --workers 4
Restart=always
User=filbert
```

## احراز هویت

هر درخواست به `/v1/*` باید یکی از کلیدهای `FILBERT_API_KEYS` را داشته باشد:

```
Authorization: Bearer <key>
```

یا `X-API-Key: <key>`. چند کلید را با کاما جدا کنید (یکی برای هر مصرف‌کننده، تا بتوانید هر کدام را جدا عوض کنید). `/health` و `/docs` بدون کلید باز هستند. اگر هیچ کلیدی تعریف نشود، API برای هر کسی که به سرور دسترسی دارد باز است؛ این حالت فقط برای شبکهٔ محلی است.

## Endpointها

| متد و مسیر | کار |
| --- | --- |
| `GET /health` | وضعیت، نسخه، فعال بودن احراز هویت/رندر/LLM |
| `POST /v1/extract` | یک صفحه: `url` (دریافت از وب) یا `html` (بدون شبکه) |
| `POST /v1/extract/batch` | چند URL همزمان (پیش‌فرض حداکثر ۲۰)؛ نتیجهٔ هر کدام جدا |
| `POST /v1/jobs` | خزش پس‌زمینه از فهرست URL و/یا سایت‌مپ |
| `GET /v1/jobs` | فهرست jobهای اخیر |
| `GET /v1/jobs/{id}` | وضعیت و پیشرفت job |
| `GET /v1/jobs/{id}/pages` | خروجی NDJSON، هر خط یک `PageRecord` |
| `GET /v1/jobs/{id}/chunks` | چانک‌های آمادهٔ embedding (NDJSON) |
| `GET /v1/jobs/{id}/errors` | URLهای ناموفق با دلیل (NDJSON) |
| `GET /v1/jobs/{id}/export.xlsx` | Excel پنل سئو: pages، issues، headings، links، images، chunks |
| `DELETE /v1/jobs/{id}` | پاک کردن خروجی job |
| `POST /v1/llm` | لایهٔ اختیاری Claude (به‌طور پیش‌فرض خاموش) |

### `POST /v1/extract`

```bash
curl -s https://filbert.example.com/v1/extract \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"url": "https://www.zoomit.ir/mobile-review/470057-xiaomi-18-pro-max-review/",
       "fields": ["seo.title", "seo.author", "seo.published_at", "content.word_count"]}'
```

```json
{"seo": {"title": "بررسی شیائومی ۱۸ پرو مکس؛ باتری شگفت‌انگیز و یک ضعف غیرمنتظره - زومیت",
         "author": "مهرداد عیسی‌لو", "published_at": "2026-11-01T21:00:00+03:30"},
 "content": {"word_count": 4472}}
```

| فیلد | توضیح |
| --- | --- |
| `url` | صفحه‌ای که دریافت شود؛ اگر `html` هم داده شود، فقط آدرس پایه برای لینک‌های نسبی و canonical است |
| `html` | HTML خام؛ هیچ درخواست شبکه‌ای زده نمی‌شود (سقف پیش‌فرض ۵ مگابایت) |
| `fields` | فقط این مسیرها برگردد، مثل `["seo", "content.text", "content.chunks"]`. بدون آن کل `PageRecord` |
| `render` | `never`، `auto` یا `always` (فقط اگر سرور extras رندر را دارد) |
| `digits` | ارقام متن نرمال‌شده: `fa` یا `en` |
| `recall` | اتحاد سه استخراج‌گر به‌جای رأی‌گیری (بیشینهٔ recall) |
| `chunk`، `chunk_max_words`، `chunk_overlap_sentences` | تنظیمات چانکینگ برای همین درخواست |
| `force` | کش و ETag نادیده گرفته شود و صفحه دوباره دانلود شود |

نمونهٔ `fields` برای کاربردهای رایج:

- پنل سئو: `["url", "canonical", "http.status", "seo", "structure.links_summary", "structure.images_summary", "content.word_count"]`
- RAG/embedding: `["url", "seo.title", "seo.published_at", "content.chunks"]`
- فقط متن: `["content.text", "content.markdown"]`

ساختار کامل `PageRecord` در [README.md](../README.md#what-you-get-per-page) آمده است.

### `POST /v1/extract/batch`

```json
{"urls": ["https://a.ir/post-1", "https://b.ir/post-2"], "fields": ["seo.title", "content.text"]}
```

پاسخ برای هر URL جدا `ok` دارد؛ یک صفحهٔ خراب کل درخواست را خراب نمی‌کند:

```json
{"results": [
   {"url": "https://a.ir/post-1", "ok": true, "record": {"seo": {"title": "..."}, "content": {"text": "..."}}},
   {"url": "https://b.ir/post-2", "ok": false, "error": "fetch_failed", "detail": "http 404", "upstream_status": 404}],
 "ok": 1, "failed": 1, "took_ms": 1840}
```

برای بیش از `FILBERT_API_MAX_BATCH` آدرس از job استفاده کنید.

### Job: خزش سایت

```bash
curl -s https://filbert.example.com/v1/jobs -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"sitemap": "https://example.ir/sitemap.xml", "pattern": "/blog/", "limit": 500, "only_changed": true}'
# → 202 {"id": "20261107-132001-4d5a", "status": "queued", "status_url": "/v1/jobs/20261107-132001-4d5a"}

curl -s https://filbert.example.com/v1/jobs/20261107-132001-4d5a -H "Authorization: Bearer $KEY"
# → {"status": "running", "total": 500, "progress": {"ok": 212, "failed": 3, "total": 500}, ...}
```

- ورودی: `urls` و/یا `sitemap` (index هم پشتیبانی می‌شود)، `limit`، `pattern` و `exclude` (regex روی URL)، `only_changed` (صفحه‌هایی که `content_hash`شان از خزش قبلی تغییر نکرده نوشته نمی‌شوند) و همهٔ گزینه‌های `/v1/extract` به‌جز `fields`.
- وضعیت‌ها: `queued`، `running`، `done`، `failed`، `interrupted` (سرور وسط کار ری‌استارت شد؛ دوباره بفرستید، با کش و `only_changed` ارزان است).
- وقتی `done` شد، آمار کامل اجرا (`ok`، `failed`، `rendered`، `p50_ms`، …) در `stats` است.
- خروجی‌ها همان فایل‌های `filbert crawl` هستند و در حین اجرا هم قابل خواندن‌اند: `pages` (با `?fields=seo&fields=url` کوچک‌تر)، `chunks`، `errors` و بعد از پایان `export.xlsx`.
- اگر `FILBERT_WEBHOOK_URL` روی سرور تنظیم باشد، هر صفحهٔ هر job به پنل شما POST می‌شود (امضای `X-Filbert-Signature` با `FILBERT_WEBHOOK_SECRET`).

### `POST /v1/llm` (اختیاری)

با `FILBERT_API_LLM=true` و `ANTHROPIC_API_KEY` روی سرور فعال می‌شود. ورودی `url` یا `html`، `schema` (`article` یا `seo`) و `instructions` اختیاری. هزینهٔ هر فراخوانی روی کلید Anthropic سرور است؛ پاسخ‌ها روی دیسک کش می‌شوند.

## کلاینت نمونه

پایتون (httpx):

```python
import time
import httpx

api = httpx.Client(
    base_url="https://filbert.example.com",
    headers={"Authorization": "Bearer <key>"},
    timeout=60,
)

rec = api.post("/v1/extract", json={"url": "https://example.ir/post", "fields": ["seo", "content.text"]}).json()

job = api.post("/v1/jobs", json={"sitemap": "https://example.ir/sitemap.xml", "limit": 200}).json()
while (st := api.get(f"/v1/jobs/{job['id']}").json())["status"] in ("queued", "running"):
    time.sleep(2)
with api.stream("GET", f"/v1/jobs/{job['id']}/chunks") as r:
    for line in r.iter_lines():
        ...  # هر خط: url، title، heading_path، text، embed_text، word_count
```

جاوااسکریپت:

```js
const res = await fetch("https://filbert.example.com/v1/extract", {
  method: "POST",
  headers: { Authorization: `Bearer ${KEY}`, "Content-Type": "application/json" },
  body: JSON.stringify({ url, fields: ["seo", "content.text"] }),
});
const rec = await res.json();
```

## خطاها

همهٔ خطاها یک شکل دارند: `{"error": "<code>", "detail": "..."}`.

| HTTP | `error` | یعنی |
| --- | --- | --- |
| 400 | `url_not_allowed` | آدرس داخلی/خصوصی یا scheme غیر HTTP (محافظ SSRF) |
| 401 | `unauthorized` | کلید نیست یا اشتباه است |
| 404 | `job_not_found`، `not_ready`، `llm_disabled` | job وجود ندارد، فایل هنوز نوشته نشده، LLM خاموش است |
| 409 | `job_running` | Excel یا حذف قبل از پایان job |
| 413 | `html_too_large`، `request_too_large`، `batch_too_large`، `job_too_large` | از سقف‌های سرور بیشتر است |
| 422 | `invalid_request`، `unknown_field`، `robots_disallowed` | ورودی نامعتبر، مسیر ناموجود در `fields`، robots.txt اجازه نمی‌دهد |
| 500 | `extract_failed` | خطای داخلی استخراج (لطفاً با URL گزارش کنید) |
| 502 | `fetch_failed`، `llm_failed` | سایت مقصد خطا داد (`upstream_status`) یا در دسترس نبود |

## تنظیمات سرور

همهٔ تنظیمات `filbert.config.Settings` با پیشوند `FILBERT_` قابل تنظیم‌اند ([.env.example](../.env.example)). مخصوص سرور:

| متغیر | پیش‌فرض | توضیح |
| --- | --- | --- |
| `FILBERT_API_KEYS` | خالی | کلیدها، جدا با کاما |
| `FILBERT_SERVE_WORKERS` | `1` (در compose: `2`) | پردازه‌های uvicorn |
| `FILBERT_API_MAX_BATCH` | `20` | سقف URL در batch |
| `FILBERT_API_MAX_HTML_BYTES` | `5000000` | سقف HTML ارسالی |
| `FILBERT_API_MAX_JOB_URLS` | `5000` | سقف URL هر job |
| `FILBERT_API_MAX_RUNNING_JOBS` | `2` | jobهای همزمان در هر پردازه؛ بقیه در صف می‌مانند |
| `FILBERT_API_JOBS_DIR` | `out/api-jobs` (Docker: `/data/jobs`) | محل خروجی jobها |
| `FILBERT_API_ALLOW_PRIVATE_URLS` | `false` | اجازهٔ درخواست به IPهای داخلی |
| `FILBERT_API_CORS_ORIGINS` | خالی | مبدأهای مجاز مرورگر، جدا با کاما |
| `FILBERT_API_LLM` | `false` | فعال کردن `/v1/llm` |
| `FILBERT_MAX_BODY_BYTES` | `20000000` | سقف حجم صفحهٔ دریافتی |
| `FILBERT_RESPECT_ROBOTS` | `true` | احترام به robots.txt |
| `FILBERT_RENDER` | `never` | حالت پیش‌فرض رندر |
| `FILBERT_PER_HOST_CONCURRENCY`، `FILBERT_PER_HOST_DELAY_MS` | `4`، `250` | ادب در برابر هر دامنه |
| `FILBERT_WORKERS` | تعداد هسته | پردازه‌های استخراج داخل هر job |

## امنیت در استقرار عمومی

- **کلید بگذارید** و سرور را پشت HTTPS قرار دهید. ساده‌ترین راه Caddy است:

  ```
  filbert.example.com {
      reverse_proxy 127.0.0.1:8000
  }
  ```

  سقف نرخ درخواست برای هر کلید را هم در همین لایه (Caddy، nginx یا Cloudflare) بگذارید؛ خود filbert محدودیت نرخ ندارد.
- **محافظ SSRF:** سروری که برای دیگران URL باز می‌کند نباید به شبکهٔ داخلی خودش برسد (مثلاً `http://169.254.169.254/` متادیتای ابری یا `http://localhost:6379`). filbert فقط `http`/`https` را قبول می‌کند، نام دامنه را resolve می‌کند و اگر به IP خصوصی، loopback، link-local یا رزرو برسد درخواست را رد می‌کند؛ این بررسی روی هر redirect و هر درخواست مرورگرِ رندر هم انجام می‌شود. دو محدودیت باقی است: DNS rebinding بین بررسی و اتصال، و redirect داخل ناوبری Chromium. برای سرور عمومی، خروجی شبکهٔ کانتینر را هم با فایروال به اینترنت عمومی محدود کنید.
- **robots.txt** به‌طور پیش‌فرض رعایت می‌شود. اگر سرور فقط برای سایت‌های خودتان است، `FILBERT_RESPECT_ROBOTS=false`.
- **سقف‌ها:** حجم بدنهٔ درخواست، حجم صفحهٔ دریافتی، اندازهٔ batch و job همه سقف دارند تا یک درخواست حافظهٔ سرور را پر نکند.
- **LLM** را فقط وقتی روشن کنید که مصرف‌کننده‌ها قابل اعتمادند؛ هزینه روی کلید شماست.

## مقیاس

- هر پردازهٔ uvicorn کلاینت HTTP، اتصال کش و thread استخراج خودش را دارد. استخراج حدود ۱۵ میلی‌ثانیه CPU برای هر صفحه است و معمولاً زمان دانلود غالب است؛ برای چند هسته `FILBERT_SERVE_WORKERS` را حدود تعداد هسته بگذارید.
- محدودیت هر دامنه (`per_host_concurrency`) داخل هر پردازه بین همهٔ کاربران مشترک است، پس با N پردازه، سقف واقعی N برابر است.
- کش HTML (`/data/cache`) بین پردازه‌ها مشترک است (SQLite WAL)؛ دریافت دوباره با ETag/304 تقریباً رایگان است.
- هر job در پردازه‌ای که آن را گرفته اجرا می‌شود و برای استخراج از استخر پردازهٔ جدا (`FILBERT_WORKERS`) استفاده می‌کند. وضعیت jobها روی دیسک است، پس هر پردازه‌ای می‌تواند وضعیت و خروجی را برگرداند.
- رندر: هر Chromium حدود ۳۰۰ مگابایت حافظه می‌خواهد؛ `FILBERT_RENDER_CONTEXTS` تعداد تب همزمان است.

## محدودیت‌های فعلی

- jobها داخل همان پردازهٔ سرور اجرا می‌شوند، نه یک صف جدا؛ با ری‌استارت `interrupted` می‌شوند.
- سهمیه و محدودیت نرخ برای هر کلید وجود ندارد (در reverse proxy بگذارید).
- webhook در سطح سرور است، نه برای هر job.
