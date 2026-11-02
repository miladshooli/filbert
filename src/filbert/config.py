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

    # استخراج
    min_text_chars: int = 200  # زیر این مقدار → fallback به recall و low_confidence
    recall: bool = False  # اتحاد سه استخراج‌گر به‌جای رأی‌گیری
    default_lang: str = "fa"
    digits: str = Field(default="fa", pattern="^(fa|en)$")
    strip_diacritics: bool = False
