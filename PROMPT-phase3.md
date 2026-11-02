فاز ۳ — متادیتای کامل + فارسی (بخش «استخراج متادیتای SEO» و «ملاحظات فارسی» BLUEPRINT). معیار خروج: دقت فیلدی بالای ۹۵٪ روی fa-200 (title/description/canonical/published_at/author).

مراحل:
1. `pyproject`: افزودن `jdatetime`؛ `lingua-language-detector` فقط در extras `[lang]` (اختیاری).
2. `meta/jsonld.py`: پارس همه `script[type=application/ld+json]` با orjson و تحمل خطا (آرایه، `@graph`، JSON خراب)؛ فهرست `@type`ها؛ کمکی‌های `author_name`, `date_published`, `date_modified`, `headline`, `keywords`. تست.
3. `meta/dates.py`: پارس ISO 8601/RFC 2822؛ regex تاریخ شمسی (`۱۴۰۵/۰۸/۱۰`، `۱۰ آبان ۱۴۰۵`، `10 آبان 1405`) و میلادی در متن؛ تبدیل شمسی→ISO با `jdatetime`؛ زنجیره `article:published_time` → JSON-LD → `<time datetime>` → regex؛ `published_at_raw` نگه داشته می‌شود. تست hypothesis برای round-trip شمسی.
4. `meta/social.py`: OG/Twitter (مطلق‌سازی `og:image`/`og:url`؛ `article:*` جدا)؛ `meta/author`: `meta[name=author]` → JSON-LD → `rel=author` → `.author/.byline`.
5. `meta/structure.py`: هدینگ‌ها (level/text/in_main)، لینک‌ها (url مطلق و نرمال، anchor، rel، internal با eTLD+1، nofollow، in_main)، تصاویر (src از `src`/`data-src`/`srcset`، alt، width/height، in_main)، خلاصه‌ها. جمع‌آوری **پیش از preclean** روی درخت کامل؛ `in_main` پس از استخراج با عضویت نود در بلوک‌های برنده.
6. `fa/lang.py`: تشخیص `fa`/`ar`/`en`/`mixed` با نسبت کاراکترهای عربی/لاتین و حروف اختصاصی فارسی (`پ چ ژ گ ک ی`) در برابر عربی (`ة ي ك ء`، تنوین)؛ درصدها ذخیره می‌شوند؛ lingua اگر نصب بود برای موارد مبهم. تست.
7. `pipeline`: اتصال همه؛ `seo.lang_detected`، `seo.author`، `seo.published_at(_raw)`، `seo.modified_at`، `seo.json_ld(_types)`، `structure.*`؛ `description` طول کاراکتر و پیکسل تقریبی. هیچ نرمال‌سازی فارسی روی متادیتا.
8. bench: gold متادیتای fa-200 با `published_at`/`author` (نیمه‌خودکار از JSON-LD/`<time>` + بازبینی در bench.label)؛ گزارش دقت فیلدی؛ `make bench` سبز.
9. در پایان: ruff/pytest سبز، اجرای واقعی روی سه URL با نمایش بخش `seo` و `structure` خلاصه، CHANGELOG، تیک فاز ۳ در CLAUDE.md، DECISIONS.

قواعد: همان CLAUDE.md؛ متادیتا = همان چیزی که گوگل می‌بیند (فقط strip و فشرده‌سازی فاصله)؛ هر مرحله یک commit.
