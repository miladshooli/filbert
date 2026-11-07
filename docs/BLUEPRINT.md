# filbert — بلوپرینت ابزار استخراج محتوای وب (دقت + سرعت)

Nov 1, 2026 · @Milad Shooli

## خلاصه اجرایی و اهداف

پیشنهاد: یک کتابخانه + CLI پایتونی به نام **filbert** که با معماری «fetch async → پارس C-backed → استخراج ترکیبی (ensemble) → خروجی سه‌فرمته» می‌سازیم. هیچ‌کدام از هفت ریپوی مرجع به‌تنهایی هم دقیق است و هم سریع؛ ترکیب درست ایده‌های آن‌ها به هدف می‌رسد.

**هدف دقت:** F1 بالای 0.95 روی بنچمارک article-extraction-benchmark (سطح Trafilatura فعلی) و F1 بالای 0.93 روی مجموعه‌تست فارسی خودمان (۲۰۰ صفحه برچسب‌خورده از نوبیتکس، خبرگزاری‌ها، فروشگاه‌ها و بلاگ‌های فارسی).

**هدف سرعت:** کمتر از 30 میلی‌ثانیه برای استخراج هر صفحه (بدون زمان شبکه، روی یک هسته CPU) و بیش از 300 صفحه در ثانیه در حالت دسته‌ای async روی یک ماشین 8 هسته‌ای؛ رندر JS فقط برای صفحاتی که لازم دارند (شناسایی خودکار).

**محدوده:** main content (متن، HTML تمیز، Markdown)، عنوان، توضیحات متا، meta keywords، canonical، robots، hreflang، Open Graph / Twitter، JSON-LD و Schema.org، هدینگ‌ها (H1 تا H6 با ساختار)، لینک‌های داخلی/خارجی با anchor text، تصاویر با alt، نویسنده، تاریخ انتشار، زبان، تعداد کلمات، و اثرانگشت محتوا (hash) برای تشخیص تغییر.

**خارج از محدوده نسخه اول:** استخراج ساختاریافته با LLM (مدل lightfeed / ScrapeGraphAI) به‌عنوان لایه اختیاری در نسخه دوم اضافه می‌شود؛ نه در مسیر اصلی، چون سرعت را از میلی‌ثانیه به ثانیه و هزینه را از صفر به توکن می‌برد.

## درس‌های هفت ریپوی مرجع

جمع‌بندی: سه ریپو الگوریتم واقعی دارند (extractnet، learnhtml، wrtnlabs)، دو ریپو لایه LLM روی تبدیل HTML→Markdown هستند (lightfeed، ScrapeGraphAI)، یکی فقط یک wrapper قدیمی Node است (mxr576) و یکی اصلاً کد باز ندارد (umbrella؛ افزونه کروم بسته با README تبلیغاتی). هیچ‌کدام فارسی را هدف نگرفته‌اند.

| ریپو | زبان / رویکرد | چه چیزی را برمی‌داریم | چرا به‌تنهایی کافی نیست |
| --- | --- | --- | --- |
| [mxr576/webpage-content-extractor](https://github.com/mxr576/webpage-content-extractor) | Node، سال ۲۰۱۵؛ wrapper روی چند کتابخانه readability با event | ایده **چند extractor موازی + fallback** و «wce-proxy» برای کش نتایج قبلی با REST | وابستگی‌های مرده (readability API تعطیل)، بدون متادیتا، بدون بنچمارک |
| [nikitautiu/learnhtml](https://github.com/nikitautiu/learnhtml) | Python؛ طبقه‌بندی گره‌های DOM با ویژگی‌های ساختاری + متنی، F1 سطح تگ 0.96 روی Dragnet | ایده **ویژگی‌های DOM** (عمق، نسبت لینک، شمار فرزند، کلاس/آیدی) به‌عنوان سیگنال مکمل، و دیتاست Dragnet برای تست | پروژه تحقیقاتی ۲۰۱۸، بدون نگهداری، نیاز به آموزش مدل؛ کند برای استفاده روزمره |
| [currentslab/extractnet](https://github.com/currentslab/extractnet) | Python؛ fork از Dragnet با CatBoost، CRF برای نویسنده، آموزش روی ۲۲ هزار صفحه | **callback pipeline** برای افزودن فیلدهای دلخواه، و خود بنچمارک article-extraction-benchmark به‌عنوان مرجع سنجش | F1 بدنه 0.927 یعنی از Trafilatura (0.948) پایین‌تر؛ وابستگی C++ و مدل سنگین؛ مخصوص خبر انگلیسی/چینی |
| [lightfeed/extractor](https://github.com/lightfeed/extractor) | TypeScript؛ HTML→Markdown تمیز → LLM با Zod schema، بازیابی JSON خراب، حل URL نسبی | **پاک‌سازی URL**، حل لینک نسبی با sourceUrl، `annotateNumberClasses` (حفظ معنای کلاس CSS کنار عدد)، و تست regression با groundtruth markdown | مسیر اصلی وابسته به LLM است؛ `extractMainHtml` فقط heuristic ساده تگ article/main |
| [ScrapeGraphAI/Scrapegraph-ai](https://github.com/ScrapeGraphAI/Scrapegraph-ai) | Python؛ گراف نودها (Fetch → Parse → RAG → Generate) با Playwright و LLM | **معماری گراف/نودی** که هر مرحله قابل تعویض است، و الگوی fetch با Playwright فقط وقتی لازم است | هر صفحه چند ثانیه و توکن می‌خورد؛ برای ۱۰ هزار URL غیرعملی |
| [umbrellaDocumentation/Web-Data-Scraper](https://github.com/umbrellaDocumentation/Web-Data-Scraper) | افزونه کروم بسته؛ فقط README | ایده **خروجی مستقیم به Sheets/Webhook** و «تشخیص بلوک‌های تکرارشونده» به‌عنوان قابلیت آینده | کدی برای مطالعه وجود ندارد |
| [wrtnlabs/web-content-extractor](https://github.com/wrtnlabs/web-content-extractor) | TypeScript؛ پیاده‌سازی مقاله CETD (Composite Text Density، SIGIR 2011)، بدون LLM | **الگوریتم چگالی متن** به‌عنوان یکی از رأی‌دهنده‌های ensemble؛ حذف تگ‌های غیرمحتوا پیش از امتیازدهی؛ خروجی `contentHtmls` چندتکه | بدون متادیتا، بدون Markdown، بدون بنچمارک منتشرشده |

اعداد بنچمارک بدنه که extractnet منتشر کرده (مجموعه [article-extraction-benchmark](https://github.com/scrapinghub/article-extraction-benchmark)):

| ابزار | Precision | Recall | F1 |
| --- | --- | --- | --- |
| trafilatura | 0.930 | 0.967 | 0.948 |
| extractnet | 0.922 | 0.933 | 0.927 |
| readability | 0.913 | 0.931 | 0.922 |
| newspaper | 0.917 | 0.906 | 0.912 |
| dragnet | 0.925 | 0.889 | 0.907 |
| boilerpipe | 0.850 | 0.870 | 0.860 |

نتیجه عملی (تصمیم نهایی): Trafilatura فعلاً دقیق‌ترین گزینه متن‌باز است، اما به‌عنوان وابستگی زمان اجرا نگه داشته **نمی‌شود**؛ فقط در `bench` به‌عنوان خط پایه مقایسه می‌ماند. سه استخراج‌گر خودمان (بازنویسی Readability، CETD و امتیاز ویژگی DOM) روی یک پارس selectolax اجرا می‌شوند تا ابزار مستقل، قابل تنظیم برای فارسی و بدون پارس دوم باشد. معیار موفقیت: در bench از Trafilatura جلو بزنیم.

## معماری کلی

معماری سه لایه است: دریافت (async با رندر مشروط)، استخراج (یک پارس، سه رأی‌دهنده، یک ادغام‌گر) و خروجی (نرمال‌سازی فارسی، سه نویسنده، ذخیره‌سازی). الگوی «نودهای قابل تعویض» ScrapeGraphAI و «callback pipeline» extractnet را نگه می‌داریم اما LLM را از مسیر اصلی حذف می‌کنیم.

&#91;embedded content: پایپ‌لاین filbert · ۳ لایه، ۱ تصمیم، ۳ استخراج‌گر موازی\]

صفحه فقط وقتی به Playwright می‌رود که دریافت ساده، متن کافی برنگرداند؛ درخت DOM یک بار ساخته می‌شود و هم به سه استخراج‌گر و هم به استخراج‌گر متادیتا می‌رسد.

**زبان و کتابخانه‌ها (Python 3.12، نصب با uv):**

| لایه | انتخاب | دلیل |
| --- | --- | --- |
| HTTP | `httpx[http2]` + `asyncio` + `anyio` semaphore | async واقعی، HTTP/2، connection pooling؛ سازگار با پروکسی و تونل شما |
| رندر JS | `playwright` (Chromium headless، استخر ۲ تا ۴ context) | فقط برای صفحاتی که heuristic «نیاز به JS» تشخیص می‌دهد |
| تشخیص encoding | `charset-normalizer` | صفحات فارسی قدیمی با windows-1256 یا بدون header درست |
| پارس DOM | `selectolax` (موتور lexbor) — **تنها پارس** | چند برابر سریع‌تر از lxml/BeautifulSoup؛ یک درخت برای هر سه استخراج‌گر و متادیتا |
| استخراج‌گر ۱ | بازنویسی الگوریتم Readability (Mozilla) در Python روی selectolax، با امتیاز class/id فارسی | بدون وابستگی خارجی؛ قوی روی مقاله و خبر |
| استخراج‌گر ۲ | پیاده‌سازی خودمان از CETD (الگوبرداری از wrtnlabs) | قوی روی صفحات غیرمقاله‌ای و لیستی |
| استخراج‌گر ۳ | امتیازدهی ویژگی‌های DOM با وزن‌های ثابت، بعداً مدل `lightgbm` کوچک | الگوبرداری از learnhtml؛ قابل آموزش روی داده فارسی |
| خط پایه (فقط dev) | `trafilatura` در extras `[bench]` | مقایسه در CI؛ هرگز در مسیر اجرا |
| متادیتا | ماژول خودمان روی `selectolax` + `orjson` برای JSON-LD | `extruct` کند است؛ ما فقط به JSON-LD و OG و meta نیاز داریم |
| Markdown | `markdownify` روی HTML تمیزِ خروجی (گزینه: `html-to-markdown` با هسته Rust) | کنترل کامل روی هدینگ، جدول، لینک، تصویر |
| مدل داده | `pydantic` v2 + `orjson` | اعتبارسنجی و JSON سریع |
| زبان | `lingua-language-detector` (یا fastText lid.176) | تشخیص fa/en/ar، به‌ویژه فارسی از عربی |
| ذخیره‌سازی | `sqlite3` (WAL) برای ایندکس + فایل‌های `.json/.html/.md` + `pyarrow` Parquet برای خروجی تحلیلی | پرس‌وجوی سریع روی ۱۰۰ هزار صفحه بدون سرور DB |
| CLI | `typer` + `rich` (progress) | جایگزین tqdm فعلی شما |

## لایه دریافت (Fetch)

اصل: شبکه گلوگاه است، نه CPU؛ پس همه‌چیز async، با کش و با رندر JS فقط در صورت نیاز.

**۱. صف و همزمانی**

- یک `asyncio.Queue` از URLها؛ کارگرها (`N = 32` پیش‌فرض) با `httpx.AsyncClient` مشترک (HTTP/2، `limits=Limits(max_connections=64, max_keepalive_connections=32)`).
- محدودیت per-host: semaphore جداگانه برای هر دامنه (پیش‌فرض ۴ همزمان، ۲۵۰ms فاصله) تا نوبیتکس یا سایت هدف بلاک نکند.
- Retry با backoff نمایی (۳ تلاش: 0.5s، 2s، 8s) فقط روی 429/5xx/timeout؛ 4xx دیگر ثبت می‌شود و رد می‌شود.
- Timeout: connect 5s، read 15s، total 30s.
- User-Agent واقعی و چرخشی؛ `Accept-Language: fa-IR,fa;q=0.9,en;q=0.5` تا نسخه فارسی سایت‌های چندزبانه برگردد.

**۲. کش دو سطحی** (الگوی wce-proxy)

- سطح ۱: کش HTTP شرطی با `ETag` و `Last-Modified` در SQLite؛ درخواست بعدی `If-None-Match` می‌فرستد و 304 یعنی بدون دانلود.
- سطح ۲: HTML خام فشرده با `zstd` در دیسک (کلید = sha256 آدرس نرمال‌شده)؛ هر استخراج مجدد (مثلاً بعد از بهبود الگوریتم) بدون شبکه انجام می‌شود. این برای شما کلیدی است: ۱۰ هزار صفحه را یک بار می‌گیرید و ده بار با نسخه‌های جدید استخراج‌گر پردازش می‌کنید.

**۳. تشخیص «نیاز به JS»** (پیش از Playwright، بدون LLM) صفحه به رندر می‌رود اگر دست‌کم یکی برقرار باشد:

- طول متن قابل‌مشاهده `body` کمتر از 400 کاراکتر باشد در حالی که HTML بیش از 50KB است،
- `div#root` / `div#app` / `div#__next` خالی باشد یا فقط `<noscript>` داشته باشد،
- نسبت `<script>` به کل بایت‌ها بیش از 0.6 باشد،
- دامنه در فهرست «همیشه رندر» کاربر باشد. رندر با استخر ۲ تا ۴ context، `wait_until='networkidle'` با سقف 10s، بلاک کردن تصویر/فونت/مدیا برای سرعت، و ذخیره HTML پس از رندر در همان کش سطح ۲ با پرچم `rendered=true`.

**۴. نرمال‌سازی URL پیش از هر چیز**

- حذف پارامترهای ردیابی (`utm_*`, `fbclid`, `gclid`, `ref`, `yclid`)، مرتب‌سازی query، حذف fragment، lowercase کردن host، حذف `index.html` و اسلش انتهایی اختیاری — همان ایده `cleanUrls` در lightfeed اما عمومی، نه فقط آمازون.
- اگر صفحه `rel=canonical` دارد و با URL فعلی فرق می‌کند، هر دو ثبت می‌شوند و کلید اصلی canonical است.

**۵. احترام به سایت**

- خواندن `robots.txt` یک بار در هر دامنه و کش ۲۴ ساعته؛ گزینه `--ignore-robots` فقط برای دامنه‌های خودتان.
- `sitemap.xml` به‌عنوان منبع ورودی پشتیبانی می‌شود (`filbert crawl --sitemap`)، چون برای ممیزی SEO معمول‌ترین نقطه شروع است.

## لایه استخراج محتوای اصلی

تصمیم: سه استخراج‌گر مستقل روی یک درخت DOM اجرا می‌شوند و در سطح «بلوک» (پاراگراف، هدینگ، لیست، جدول، نقل‌قول، کد) رأی می‌دهند؛ بلوکی که دست‌کم دو رأی بگیرد وارد خروجی می‌شود. دلیل: هر الگوریتم روی یک نوع صفحه شکست می‌خورد (Readability روی لندینگ و فروشگاه، CETD روی مقاله‌های کوتاه با سایدبار پرمتن، DOM-scorer روی ساختارهای غیرمعمول) و خطاهایشان همبسته نیست.

**گام ۰ — پیش‌پاک‌سازی مشترک** (یک بار، قبل از هر سه)

- حذف کامل: `script, style, noscript, template, iframe, svg, canvas, form, input, select, button, nav, aside, footer` و عناصر با `aria-hidden="true"`، `hidden`، `display:none` inline.
- حذف با الگوی class/id (regex، بدون حساسیت به حروف): `comment|share|social|related|sidebar|breadcrumb|cookie|popup|modal|newsletter|promo|advert|banner|menu|pagination` — به‌علاوه الگوهای فارسی رایج در تم‌های وردپرس ایرانی: `nazar|didgah|eshterak|tabligh|matalebe-mortabet`.
- **استثنا:** `header` و `h1` داخل `article/main` حذف نمی‌شوند (خطای رایج wrtnlabs که `header` را کور حذف می‌کند و تیتر مقاله را از دست می‌دهد).
- نگه داشتن `table`، `pre`، `code`، `blockquote`، `figure/figcaption` چون در محتوای فنی و فروشگاهی (مشخصات محصول نوبیتکس، جدول کارمزد) خودِ محتوا هستند.

**گام ۱ — بازنویسی Readability** (ماژول `readability.py`) همان الگوریتم Mozilla Readability اما روی selectolax و با پارامترهای خودمان: برای هر `p/div/td/pre/blockquote` امتیاز پایه از نوع تگ، +۱ به‌ازای هر ویرگول (`,` و `،`)، +۱ به‌ازای هر ۱۰۰ کاراکتر تا سقف ۳، ضرب در `(1 − link_density)`؛ امتیاز به والد (کامل) و پدربزرگ (نصف) منتشر می‌شود؛ بهترین کاندید انتخاب و خواهر و برادرهایی با امتیاز بالای ۲۰٪ بهترین به آن الحاق می‌شوند. وزن‌های class/id از `boilerplate_fa.yml` می‌آیند، نه هاردکد. خروجی: لیست بلوک با XPath. هدف: زیر ۳ms برای صفحه ۲۰۰KB.

**گام ۲ — چگالی متن ترکیبی (CETD)** برای هر گره: `TD = chars / tags` و `CTD = TD × log(chars_without_links / link_chars) × ...` طبق مقاله Sun و همکاران (SIGIR 2011). آستانه = CTD گره body. زیردرختِ با بیشترین مجموع CTD بالای آستانه انتخاب می‌شود؛ سپس گره‌های همسایه با CTD بالای آستانه به آن الحاق می‌شوند (برای مقاله‌های دوبخشی). پیاده‌سازی روی `selectolax` با یک پیمایش post-order؛ زیر ۵ms برای صفحه ۲۰۰KB.

**گام ۳ — امتیاز ویژگی DOM** (الگوی learnhtml، نسخه بدون مدل در فاز اول) برای هر بلوک این ویژگی‌ها محاسبه می‌شود: طول متن، نسبت کاراکتر لینک، تعداد نقطه/ویرگول (علائم جمله؛ برای فارسی «.» و «،» و «؛»)، عمق در درخت، تعداد خواهر و برادر هم‌تگ، میانگین طول کلمه، وجود عدد/قیمت، فاصله از بزرگ‌ترین بلوک متنی، و امتیاز class/id مثبت (`content|article|post|entry|body|main|matn|mohtava`). وزن‌های اولیه دستی (نسخه ساده Readability)؛ فاز سوم با `lightgbm` روی ۲۰۰ صفحه برچسب‌خورده فارسی آموزش می‌بیند و همین ویژگی‌ها ورودی مدل می‌شوند.

**گام ۴ — رأی‌گیری و ادغام**

- کلید هر بلوک = XPath نرمال‌شده + hash متن.
- بلوک با ۳ رأی: قطعی. با ۲ رأی: قطعی. با ۱ رأی: فقط اگر از Readability باشد **و** طول بیش از ۸۰ کاراکتر **و** بین دو بلوک قطعی قرار گرفته باشد (پر کردن حفره).
- ترتیب خروجی = ترتیب سند، نه ترتیب رأی.
- اگر مجموع متن خروجی زیر ۲۰۰ کاراکتر شد → fallback به حالت `--recall` (اتحاد سه خروجی) و پرچم `low_confidence=true` در JSON.
- امتیاز اطمینان `confidence` در خروجی = میانگین نسبت توافق بلوک‌ها؛ این عدد برای شما در ممیزی SEO مهم است تا صفحات مشکوک را دستی ببینید.

**گام ۵ — ساخت HTML تمیز** از بلوک‌های برنده، یک درخت HTML جدید ساخته می‌شود: فقط تگ‌های معنایی (`h1-h6, p, ul/ol/li, table/thead/tbody/tr/th/td, blockquote, pre/code, figure/img/figcaption, a, strong, em`)، بدون هیچ attribute جز `href`, `src`, `alt`, `colspan/rowspan`، و `lang="fa" dir="rtl"` روی ریشه. این HTML هم خروجی `.html` است و هم ورودی تبدیل Markdown؛ یعنی MD همیشه با HTML تمیز سازگار است.

**کنترل سرعت:** هر سه استخراج‌گر و استخراج‌گر متادیتا روی یک درخت `selectolax` اجرا می‌شوند؛ هیچ پارس دومی وجود ندارد (دلیل اصلی کنار گذاشتن Trafilatura از مسیر اجرا). روی ماشین 8 هسته‌ای، استخراج با `ProcessPoolExecutor` (یک پردازه به‌ازای هر هسته) از دریافت async جدا می‌شود تا GIL گلوگاه نشود.

## استخراج متادیتای SEO

متادیتا از `<head>` و از درخت کامل (نه از خروجی main content) گرفته می‌شود؛ هر فیلد یک زنجیره اولویت دارد و منبع انتخاب‌شده در JSON ثبت می‌شود تا در ممیزی بدانید عنوان از `og:title` آمده یا از `h1`.

| فیلد | زنجیره اولویت (اولی که پیدا شد) | نکته |
| --- | --- | --- |
| `title` | `<title>` → `og:title` → `twitter:title` → اولین `h1` | هر سه نسخه جداگانه هم ذخیره می‌شود (`title_tag`, `og_title`, `h1`) چون اختلافشان خودش یک یافته SEO است |
| `description` | `meta[name=description]` → `og:description` → `twitter:description` | طول کاراکتر و پیکسل تقریبی (فونت فارسی پهن‌تر است) محاسبه می‌شود |
| `keywords` | `meta[name=keywords]` → `article:tag` (چندتایی) → `keywords` در JSON-LD | با ویرگول فارسی «،» و انگلیسی هر دو جدا می‌شود |
| `canonical` | `link[rel=canonical]` → `og:url` | مطلق‌سازی با URL صفحه |
| `robots` | `meta[name=robots]` + `googlebot` + هدر `X-Robots-Tag` | پرچم‌های `noindex/nofollow` جدا bool می‌شوند |
| `hreflang` | همه `link[rel=alternate][hreflang]` | آرایه `{lang, url}` |
| `lang` | `html[lang]` → `og:locale` → تشخیص خودکار از متن | مقدار اعلام‌شده و تشخیص‌داده‌شده هر دو ذخیره می‌شوند |
| `open_graph` | همه `meta[property^=og:]` و `article:*` | dict خام |
| `twitter` | همه `meta[name^=twitter:]` | dict خام |
| `json_ld` | هر `script[type=application/ld+json]`، پارس با `orjson`، تحمل خطا | آرایه از اشیاء؛ `@type`ها جداگانه فهرست می‌شوند (`Article`, `Product`, `FAQPage`, `BreadcrumbList`, ...) |
| `microdata` | `itemscope/itemprop` فقط در صورت نبود JSON-LD | فاز دوم |
| `author` | `meta[name=author]` → JSON-LD `author.name` → `rel=author` → `.author/.byline` | ایده CRF در extractnet برای فاز سوم |
| `published_at` / `modified_at` | `article:published_time` → JSON-LD `datePublished` → `<time datetime>` → regex تاریخ شمسی/میلادی در متن | تاریخ شمسی با `jdatetime` به ISO تبدیل می‌شود؛ هر دو نگه داشته می‌شوند |
| `headings` | همه `h1`–`h6` به ترتیب سند، با `level`, `text`, `in_main_content: bool` | ساختار outline برای ممیزی سلسله‌مراتب |
| `links` | همه `<a href>`: `url` مطلق، `anchor`, `rel`, `internal: bool`, `in_main_content: bool`, `nofollow: bool` | تمایز داخلی/خارجی با مقایسه eTLD+1 (`tldextract`) |
| `images` | همه `<img>`: `src` مطلق (`srcset` و `data-src` و `loading=lazy` هم)، `alt`, `width/height`, `in_main_content` | تعداد تصاویر بدون alt خلاصه می‌شود |
| `word_count` / `char_count` | روی متن main content پس از نرمال‌سازی | شمارش کلمه فارسی با تقسیم بر فاصله و ZWNJ، نه فقط فاصله |
| `reading_time_min` | `word_count / 200` | - |
| `content_hash` | `xxhash64` متن نرمال‌شده main content | تشخیص تغییر در خزش‌های بعدی بدون مقایسه کامل |
| `http` | status، `content-type`، `content-length`، زمان پاسخ، redirect chain، `last-modified`, `etag` | برای ممیزی فنی |

**قوانین تکمیلی**

- هر URL (href، src، canonical، og:url) با `urljoin` روی URL نهایی پس از redirect مطلق می‌شود، بعد همان نرمال‌سازی لایه دریافت رویش اعمال می‌شود.
- فیلدهای متنی `strip` و فشرده‌سازی فاصله می‌شوند اما **بدون** نرمال‌سازی فارسی؛ متادیتا باید همان چیزی باشد که گوگل می‌بیند. نرمال‌سازی فقط روی `main_text` اعمال می‌شود و نسخه خام هم نگه داشته می‌شود.
- هیچ فیلدی حذف نمی‌شود؛ نبودِ مقدار `null` است، نه رشته خالی، تا تحلیل «صفحات بدون description» با یک فیلتر ساده ممکن باشد.

## فرمت‌های خروجی و ذخیره‌سازی

یک مدل داده (`PageRecord` در pydantic) منبع هر سه خروجی است؛ JSON کامل‌ترین است، HTML و Markdown از همان رکورد رندر می‌شوند. هیچ فرمتی چیزی ندارد که JSON نداشته باشد.

**۱. JSON** (`orjson`، یک فایل به‌ازای هر صفحه + یک JSONL تجمعی)

```json
{
  "schema_version": "1.0",
  "url": "https://nobitex.ir/blog/...",
  "final_url": "https://nobitex.ir/blog/...",
  "canonical": "https://nobitex.ir/blog/...",
  "fetched_at": "2026-11-01T10:22:14+03:30",
  "http": {"status": 200, "content_type": "text/html; charset=utf-8", "response_ms": 412, "redirects": [], "rendered": false},
  "seo": {
    "title": "...", "title_source": "title_tag", "title_tag": "...", "og_title": "...", "h1": "...",
    "description": "...", "description_source": "meta",
    "keywords": ["..."], "robots": {"raw": "index,follow", "noindex": false, "nofollow": false},
    "hreflang": [], "lang_declared": "fa", "lang_detected": "fa",
    "open_graph": {}, "twitter": {}, "json_ld": [], "json_ld_types": ["Article"],
    "author": null, "published_at": null, "modified_at": null
  },
  "content": {
    "text": "متن نرمال‌شده main content",
    "text_raw": "متن بدون نرمال‌سازی",
    "html": "<article lang=\"fa\" dir=\"rtl\">...</article>",
    "markdown": "# ...",
    "blocks": [{"type": "p", "text": "...", "xpath": "...", "votes": 3}],
    "word_count": 1240, "char_count": 7310, "reading_time_min": 6,
    "confidence": 0.94, "low_confidence": false,
    "extractors": {"trafilatura": 0.97, "cetd": 0.91, "dom": 0.93}
  },
  "structure": {
    "headings": [{"level": 1, "text": "...", "in_main": true}],
    "links": [{"url": "...", "anchor": "...", "internal": true, "nofollow": false, "in_main": true}],
    "images": [{"src": "...", "alt": "", "in_main": true}],
    "links_summary": {"internal": 42, "external": 7, "nofollow": 3, "in_main": 11},
    "images_summary": {"total": 9, "missing_alt": 2}
  },
  "content_hash": "a3f9...",
  "raw_html_ref": "cache/sha256-of-url.html.zst"
}
```

**۲. HTML تمیز** — همان `content.html` با یک پوسته حداقلی: `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>…</title></head><body>` + `<article>` + یک `<footer>` کوچک با `source-url` و `fetched-at` در `data-*`. بدون CSS و JS؛ قابل باز شدن در مرورگر و قابل ایندکس برای مقایسه.

**۳. Markdown** — front-matter YAML (title, url, canonical, description, published\_at, lang, word\_count, confidence) + بدنه تبدیل‌شده از HTML تمیز. قواعد: هدینگ‌ها همان سطح اصلی، جدول‌ها به pipe table (اگر سلول چندخطی بود، HTML خام جدول داخل MD می‌ماند)، تصاویر `![alt](src)`، لینک‌های داخلی به‌صورت مطلق. ZWNJ حفظ می‌شود (الزامی برای «می‌شود» و امثالش).

**۴. ذخیره‌سازی روی دیسک**

```
output/
  <run-id>/
    pages.jsonl          # یک خط به‌ازای هر صفحه، آماده pandas/duckdb
    pages.parquet        # همان داده ستونی برای تحلیل سریع
    json/<slug>.json
    html/<slug>.html
    md/<slug>.md
    errors.jsonl         # URLهای ناموفق با دلیل
    run.json             # تنظیمات، نسخه ابزار، آمار (n, ok, failed, rendered, p50/p95 ms)
cache/
  raw/<sha256>.html.zst  # HTML خام
  index.sqlite           # url, final_url, etag, last_modified, fetched_at, content_hash
```

- `<slug>` = host + مسیر پاکسازی‌شده، حداکثر ۱۲۰ کاراکتر، + ۸ کاراکتر اول hash برای یکتایی؛ ویندوز‌سازگار (بدون `: ? * < > |`).
- `index.sqlite` با WAL؛ جدول `pages(url PRIMARY KEY, content_hash, fetched_at, run_id)` تا خزش بعدی فقط صفحات تغییرکرده را دوباره استخراج کند (`--only-changed`).
- خروجی به Excel/Sheets (ایده umbrella) در فاز دوم از روی `pages.parquet` با `openpyxl`؛ ستون‌های فارسی با `utf-8-sig` و بدون مشکل ZWNJ که قبلاً دیده‌اید.
- Webhook/POST به API دلخواه (برای اتصال به پنل SEO آینده شما) از همان `PageRecord` سریال می‌شود.
- سرور HTTP (`filbert serve`، extras `server`، از 0.6.0): همان `PageRecord` از طریق `POST /v1/extract`، batch و jobهای خزش؛ با کلید API و محافظ SSRF. جزئیات: `docs/API.md`.

## ملاحظات فارسی و RTL

هیچ‌کدام از هفت ریپو برای فارسی تنظیم نشده‌اند؛ این بخش همان چیزی است که ابزار شما را از Trafilatura خام متمایز می‌کند.

**نرمال‌سازی متن** (ماژول `fa_normalize`، فقط روی `content.text` و `content.markdown`؛ نسخه خام همیشه نگه داشته می‌شود)

- یکسان‌سازی حروف عربی/فارسی: `ي → ی`، `ك → ک`، `ة → ه`، `ؤ/ئ` بدون تغییر، حذف تشدید/فتحه/کسره/ضمه اختیاری (`--strip-diacritics`).
- ارقام: عربی‌هندی `٠١٢` و فارسی `۰۱۲` به یک شکل واحد (پیش‌فرض: فارسی؛ گزینه `--digits=en` برای تحلیل عددی).
- ZWNJ (`U+200C`): حفظ می‌شود؛ ZWNJ تکراری و ZWNJ کنار فاصله حذف می‌شود؛ فاصله بین پیشوند «می» و فعل به ZWNJ تبدیل **نمی‌شود** (تغییر معنایی است و خارج از وظیفه استخراج‌گر).
- کاراکترهای ناپیدا: `U+200B` (ZWSP)، `U+200E/200F` (LRM/RLM)، `U+FEFF` (BOM)، `U+00A0` (NBSP → فاصله) حذف یا تبدیل می‌شوند.
- فاصله‌های تکراری و خطوط خالی بیش از دو تا فشرده می‌شوند؛ علائم فارسی «،؛؟» پس از آن‌ها فاصله می‌گیرد.

**شمارش کلمه**: تقسیم بر فاصله + ZWNJ به‌عنوان مرز کلمه حساب **نمی‌شود** (پس «می‌شود» یک کلمه است). عدد و کلمه انگلیسی هر کدام یک کلمه.

**تشخیص زبان**: بر پایه نسبت کاراکترهای `U+0600–U+06FF` و حضور حروف اختصاصی فارسی (`پ چ ژ گ ک ی`) در برابر عربی (`ة ي ك ء`)؛ اگر مبهم بود، `lingua` روی ۵۰۰ کاراکتر اول. نتیجه `fa` / `ar` / `en` / `mixed` و درصد هر کدام ذخیره می‌شود؛ صفحات نوبیتکس معمولاً `mixed` با اصطلاحات انگلیسی هستند.

**تاریخ شمسی**: regex برای `۱۴۰۵/۰۸/۱۰`، `۱۰ آبان ۱۴۰۵`، `10 آبان 1405` و معادل‌های عددی؛ تبدیل با `jdatetime` به ISO 8601 در `published_at`، و مقدار اصلی در `published_at_raw`.

**RTL در خروجی‌ها**

- HTML تمیز: `dir="rtl"` روی ریشه و `dir="auto"` روی هر بلوک تا بلوک‌های انگلیسی (کد، لینک) درست نمایش داده شوند.
- Markdown: بدون نشانه‌گذاری جهت (MD استاندارد ندارد)؛ ویرایشگرها خودشان bidi می‌کنند. اعداد در جدول‌ها راست‌چین نیستند؛ این محدودیت MD است و در front-matter `dir: rtl` ثبت می‌شود.
- JSON: UTF-8 بدون escape کردن کاراکترهای غیر ASCII (`orjson` پیش‌فرض همین است)؛ خروجی خوانا می‌ماند.

**encoding صفحات قدیمی**: اگر هدر یا `<meta charset>` نبود یا با محتوا نمی‌خواند، `charset-normalizer` تصمیم می‌گیرد؛ `windows-1256` هنوز در سایت‌های قدیمی ایرانی دیده می‌شود. encoding تشخیص‌داده‌شده در `http.detected_encoding` ثبت می‌شود.

**تم‌های وردپرس ایرانی**: فهرست class/id boilerplate با نام‌های فینگلیش رایج (`nazarat`, `didgah-ha`, `matalebe-mortabet`, `eshterak-khabarname`, `tabligh`) در یک فایل YAML قابل ویرایش `boilerplate_fa.yml` نگه داشته می‌شود تا بدون تغییر کد گسترش یابد.

## بنچمارک، تست و معیارهای کیفیت

قاعده: هیچ تغییری در استخراج‌گر بدون اجرای بنچمارک merge نمی‌شود؛ `make bench` هم دقت را گزارش می‌دهد هم سرعت را، و افت بیش از 0.5 امتیاز F1 یا ۱۰٪ سرعت، CI را قرمز می‌کند.

**مجموعه‌های دقت**

| مجموعه | اندازه | منبع | نقش |
| --- | --- | --- | --- |
| article-extraction-benchmark | 181 صفحه انگلیسی با groundtruth | [scrapinghub](https://github.com/scrapinghub/article-extraction-benchmark) | مقایسه با اعداد منتشرشده Trafilatura / extractnet؛ ابزار ارزیابی آماده دارد |
| Dragnet / CleanEval | چند صد صفحه | دیتاست‌های کلاسیک که learnhtml و extractnet روی آن‌ها سنجیده شده‌اند | سنجش CETD و DOM-scorer به‌تنهایی |
| lightfeed test-data | HTML + groundtruth markdown | [lightfeed/extractor-test-data](https://github.com/lightfeed/extractor-test-data) | تست regression تبدیل HTML→Markdown |
| **fa-200** (می‌سازیم) | 200 صفحه فارسی: 60 خبر، 40 بلاگ، 40 محصول/فروشگاه، 30 لندینگ و صفحه خدمات (شامل نوبیتکس)، 30 انجمن/پرسش‌وپاسخ | برچسب‌گذاری دستی: فایل `.txt` متن اصلی + `.json` متادیتای درست | **معیار اصلی تصمیم‌گیری**؛ بدون آن اعداد انگلیسی گمراه‌کننده‌اند |

**معیارها**

- متن اصلی: Precision / Recall / F1 در سطح توکن (همان روش article-extraction-benchmark، با `difflib` روی توکن‌های نرمال‌شده) و Accuracy در سطح صفحه (F1 بالای 0.9).
- متادیتا: دقت فیلد به فیلد (`title`, `description`, `canonical`, `published_at`, `author`) به‌صورت exact match پس از strip؛ هدینگ‌ها و لینک‌ها با Jaccard روی مجموعه.
- Markdown: نسبت تطابق خطی با groundtruth پس از نرمال‌سازی فاصله (هدف بالای 0.95).
- اطمینان: همبستگی `confidence` گزارش‌شده با F1 واقعی (Spearman بالای 0.6)، تا این عدد در ممیزی قابل اعتماد باشد.

**معیارهای سرعت** (روی HTML کش‌شده، بدون شبکه، `pytest-benchmark`)

- p50 و p95 زمان استخراج هر صفحه برای هر استخراج‌گر جداگانه و برای ensemble.
- throughput صفحه بر ثانیه با ۱، ۴ و ۸ پردازه.
- پیک حافظه هر پردازه (`tracemalloc`)؛ سقف 300MB برای صفحه 2MB.
- اهداف: ensemble زیر 30ms p50 و زیر 120ms p95 روی صفحه معمول 150KB؛ بالای 300 صفحه/ثانیه با ۸ پردازه.

**تست‌های واحد و خصوصیتی**

- `pytest` + `hypothesis` روی `fa_normalize` (نرمال‌سازی دوبار = یک بار؛ هیچ‌وقت ZWNJ معتبر حذف نشود).
- هر قانون boilerplate یک fixture HTML کوچک دارد (مثبت و منفی).
- تست golden برای ۲۰ صفحه منتخب: خروجی JSON کامل snapshot می‌شود و هر diff باید عمداً تأیید شود.
- تست end-to-end با سرور HTTP محلی (`pytest-httpserver`) برای retry، 304، redirect، encoding و تشخیص JS.

**گزارش بنچمارک**: `bench/report.md` خودکار تولید می‌شود با جدول F1 هر استخراج‌گر به تفکیک نوع صفحه، تا ببینید روی کدام دسته (مثلاً فروشگاه) باید وزن‌ها را تغییر دهید.

## ساختار پروژه، نقشه راه و پرامپت شروع

**ساختار پروژه**

```
filbert/
  pyproject.toml            # uv, python>=3.12, extras: [render] playwright, [ml] lightgbm, [bench] trafilatura
  src/filbert/
    __init__.py
    cli.py                  # typer: extract, crawl, bench, export
    config.py               # pydantic-settings; خواندن از .env و فلگ‌ها
    models.py               # PageRecord و زیرمدل‌ها (schema_version)
    fetch/
      client.py             # httpx AsyncClient, per-host limiter, retry
      cache.py              # SQLite index + zstd raw store, ETag/304
      render.py             # Playwright pool (اختیاری)
      needs_js.py           # heuristic تشخیص نیاز به رندر
      urlnorm.py            # نرمال‌سازی URL، تشخیص داخلی/خارجی
      robots.py
    extract/
      preclean.py           # گام ۰ + boilerplate_fa.yml
      readability.py        # بازنویسی Readability روی selectolax → blocks
      cetd.py               # چگالی متن ترکیبی روی selectolax
      domscore.py           # ویژگی‌های DOM + وزن‌ها / مدل
      ensemble.py           # رأی‌گیری، ادغام، confidence
      cleanhtml.py          # ساخت HTML معنایی تمیز
    meta/
      head.py               # title/description/keywords/canonical/robots/hreflang
      social.py             # OG/Twitter
      jsonld.py
      dates.py              # میلادی + شمسی
      structure.py          # headings/links/images
    fa/
      normalize.py
      lang.py
      tokenize.py           # شمارش کلمه با ZWNJ
    out/
      json_writer.py
      html_writer.py
      md_writer.py
      store.py              # layout دیسک، jsonl، parquet
    pipeline.py             # اتصال لایه‌ها، ProcessPool
  bench/                    # دیتاست‌ها + eval.py + report؛ trafilatura فقط اینجا
  tests/
  data/boilerplate_fa.yml
```

**رابط استفاده**

```
filbert extract https://example.ir/post --out out/ --formats json,html,md
filbert crawl --sitemap https://nobitex.ir/sitemap.xml --concurrency 32 --only-changed
filbert bench --dataset fa-200 --compare-with trafilatura
```

```python
from filbert import extract_html, fetch_and_extract
rec = extract_html(html, url="https://...")       # بدون شبکه، همزمان
rec.content.markdown; rec.seo.title; rec.model_dump_json()
```

**نقشه راه (۵ فاز، هر فاز قابل تحویل)**

1. **هسته (هفته ۱–۲):** مدل داده، fetch async با کش، preclean، استخراج‌گر Readability خودمان، سه نویسنده خروجی، CLI `extract`. معیار خروج: ۱۰۰۰ صفحه نوبیتکس بدون خطا، JSON معتبر.
2. **ensemble (هفته ۳–۴):** CETD و DOM-scorer، رأی‌گیری، confidence، ابزار برچسب‌زنی و ساخت fa-200، `bench` با Trafilatura به‌عنوان خط پایه. معیار خروج: F1 روی fa-200 دست‌کم ۳ امتیاز بالاتر از Trafilatura.
3. **متادیتای کامل و فارسی (هفته ۵):** همه فیلدهای جدول متادیتا، تاریخ شمسی، تشخیص زبان، نرمال‌سازی. معیار خروج: دقت فیلدی بالای ۹۵٪ روی fa-200.
4. **رندر و مقیاس (هفته ۶):** Playwright مشروط، ProcessPool، `crawl --sitemap`، `--only-changed`، گزارش run. معیار خروج: ۳۰۰ صفحه/ثانیه روی کش، ۱۰ هزار URL در یک اجرا.
5. **هوش اختیاری (بعد):** مدل lightgbm برای DOM-scorer، CRF نویسنده، لایه LLM با schema (الگوی lightfeed) به‌عنوان `--llm` اختیاری، خروجی Excel/Webhook برای پنل SEO.

**تصمیم‌های گرفته‌شده و باز**

- [x] Trafilatura: در مسیر اجرا نیست؛ فقط خط پایه در `bench`. استخراج‌گر Readability خودمان جای آن را می‌گیرد تا ابزار مستقل و برای فارسی قابل تنظیم باشد.
- [x] برچسب‌گذاری fa-200 دستی انجام می‌شود؛ ابزار برچسب‌زنی (یک صفحه HTML با انتخاب بلوک، خروجی `.txt` + `.json`) در فاز ۲ ساخته می‌شود.
- [ ] تست پایداری ۲ ساعته Playwright روی ویندوز با VPN: اسکریپت `playwright_stability_test.py` آماده است؛ نتیجه (نرخ موفقیت، p95، تعداد ری‌استارت) پس از اجرا اینجا ثبت می‌شود. اجرای کوتاه ۴ دقیقه‌ای روی macOS (2026-11-02): ۵۵ صفحه، موفقیت ۹۶.۴٪، ۲ timeout، ۰ کرش، p50 13.4s — [docs/stability-2026-11-02.md](stability-2026-11-02.md).

**پرامپت شروع برای Claude Code** (در ریشه پروژه خالی، پس از `uv init`)

```markdown
این سند بلوپرینت پروژه filbert است (پیوست/لینک). فاز ۱ را پیاده‌سازی کن:
1. ساختار پوشه‌ها را دقیقاً مطابق بخش «ساختار پروژه» بساز؛ pyproject با uv، python 3.12، ruff، pytest. trafilatura فقط در extras [bench].
2. models.py را از JSON نمونه بخش «فرمت‌های خروجی» با pydantic v2 بساز؛ schema_version="1.0".
3. fetch/client.py و fetch/cache.py را طبق بخش «لایه دریافت» بنویس (httpx async، per-host semaphore، retry، ETag/304، zstd store، SQLite WAL). برای هر مورد تست با pytest-httpserver.
4. extract/preclean.py با فهرست تگ‌ها و regex های بخش «گام ۰»؛ boilerplate_fa.yml را بساز.
5. extract/readability.py: بازنویسی الگوریتم Readability روی selectolax طبق «گام ۱» → لیست Block(type, text, xpath). تست با ۵ fixture HTML فارسی.
6. out/*: سه نویسنده از PageRecord؛ md با front-matter؛ html با lang=fa dir=rtl.
7. cli.py با typer: `extract <url|file>` و `--formats`.
قواعد: هیچ LLM در مسیر اصلی؛ فقط یک پارس با selectolax (lxml ممنوع)؛ هر ماژول تست دارد؛ ZWNJ هرگز حذف نشود؛ خروجی JSON با orjson بدون escape یونیکد. در پایان `pytest -q` و یک اجرای واقعی روی ۳ URL فارسی را نشان بده.
```

**منابع**

- [mxr576/webpage-content-extractor](https://github.com/mxr576/webpage-content-extractor) · [nikitautiu/learnhtml](https://github.com/nikitautiu/learnhtml) · [currentslab/extractnet](https://github.com/currentslab/extractnet) · [lightfeed/extractor](https://github.com/lightfeed/extractor) · [ScrapeGraphAI/Scrapegraph-ai](https://github.com/ScrapeGraphAI/Scrapegraph-ai) · [umbrellaDocumentation/Web-Data-Scraper](https://github.com/umbrellaDocumentation/Web-Data-Scraper) · [wrtnlabs/web-content-extractor](https://github.com/wrtnlabs/web-content-extractor)
- بنچمارک مرجع: [scrapinghub/article-extraction-benchmark](https://github.com/scrapinghub/article-extraction-benchmark)؛ مقاله CETD: [DOM Based Content Extraction via Text Density (SIGIR 2011)](https://ofey.me/assets/pdf/cetd-sigir11.pdf)؛ مقاله learnhtml: [Learning Web Content Extraction with DOM Features](https://www.researchgate.net/publication/329061153_Learning_Web_Content_Extraction_with_DOM_Features)
