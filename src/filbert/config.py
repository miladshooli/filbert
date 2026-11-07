"""تنظیمات filbert با pydantic-settings؛ از `.env` و متغیرهای `FILBERT_*` خوانده می‌شود.

هیچ global state؛ یک نمونه `Settings` ساخته و به لایه‌ها تزریق می‌شود.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FILBERT_", env_file=".env", extra="ignore")

    # مسیرها
    cache_dir: Path = Path("cache")
    boilerplate_path: Path | None = None  # None → فایل همراه بسته

    # شبکه
    http2: bool = True
    max_connections: int = 64
    max_keepalive_connections: int = 32
    per_host_concurrency: int = 4
    per_host_delay_ms: int = 250
    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    total_timeout: float = 30.0
    retry_backoff: tuple[float, ...] = (0.5, 2.0, 8.0)  # ۳ تلاش مجدد
    user_agents: tuple[str, ...] = DEFAULT_USER_AGENTS
    accept_language: str = "fa-IR,fa;q=0.9,en;q=0.5"
    concurrency: int = 32  # کارگران سراسری
    respect_robots: bool = True
    workers: int | None = None  # پردازه‌های استخراج؛ None = تعداد هسته؛ 0/1 = inline
    render: str = Field(default="never", pattern="^(never|auto|always)$")
    render_contexts: int = 3
    render_timeout: float = 10.0
    always_render_domains: tuple[str, ...] = ()
    max_body_bytes: int = 20_000_000  # سقف حجم پاسخ؛ بیشتر → FetchError (۰ = بی‌سقف)
    block_private_urls: bool = False  # SSRF: آدرس‌های داخلی/خصوصی رد شوند (در سرور API روشن است)

    # استخراج
    dom_model_path: Path | None = None  # مدل lightgbm اختیاری برای DOM-scorer (extras ml)
    min_text_chars: int = 200  # زیر این مقدار → fallback به recall و low_confidence
    recall: bool = False  # اتحاد سه استخراج‌گر به‌جای رأی‌گیری
    default_lang: str = "fa"
    digits: str = Field(default="fa", pattern="^(fa|en)$")
    strip_diacritics: bool = False

    # webhook (پنل SEO)
    webhook_url: str | None = None
    webhook_secret: str | None = None
    webhook_batch: int = 10

    # چانکینگ (docs/CHUNKING.md)
    chunk: bool = True
    chunk_max_words: int = 250
    chunk_hard_max: int = 400
    chunk_overlap_sentences: int = 1
    chunk_heading_level: int = 3
    chunk_unit: str = Field(default="words", pattern="^(words|chars|tiktoken)$")
    chunk_context_prefix: bool = True

    # سرور API (`filbert serve`، extras server؛ docs/API.md)
    api_keys: str = ""  # کلیدها با کاما جدا؛ خالی = بدون احراز هویت (فقط برای شبکه محلی)
    api_allow_private_urls: bool = False  # True = سرور به IPهای داخلی هم درخواست می‌زند
    api_max_batch: int = 20  # سقف URL در `/v1/extract/batch`
    api_max_html_bytes: int = 5_000_000  # سقف HTML ارسالی در بدنه درخواست
    api_max_job_urls: int = 5_000  # سقف URL هر job خزش
    api_max_running_jobs: int = 2  # jobهای همزمان در هر پردازه
    api_jobs_dir: Path = Path("out/api-jobs")
    api_cors_origins: str = ""  # مبدأهای مجاز CORS با کاما؛ خالی = CORS خاموش
    api_llm: bool = False  # `/v1/llm` فعال باشد (هزینه API روی کلید سرور است)
