"""مدل داده filbert — `PageRecord` منبع هر سه خروجی (JSON/HTML/Markdown) است.

قاعده: هر فیلد غایب `None` است، نه رشته خالی، تا فیلتر «صفحات بدون description» ساده باشد.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"

BlockType = Literal[
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "blockquote", "pre", "figure"
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class HttpInfo(_Base):
    status: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    response_ms: int | None = None
    redirects: list[str] = Field(default_factory=list)
    rendered: bool = False
    last_modified: str | None = None
    etag: str | None = None
    detected_encoding: str | None = None
    from_cache: bool = False


class Robots(_Base):
    raw: str | None = None
    noindex: bool = False
    nofollow: bool = False


class Hreflang(_Base):
    lang: str
    url: str


class SeoMeta(_Base):
    title: str | None = None
    title_source: str | None = None
    title_tag: str | None = None
    og_title: str | None = None
    h1: str | None = None
    description: str | None = None
    description_source: str | None = None
    keywords: list[str] | None = None
    keywords_source: str | None = None
    canonical: str | None = None
    canonical_source: str | None = None
    robots: Robots = Field(default_factory=Robots)
    hreflang: list[Hreflang] = Field(default_factory=list)
    title_length: int | None = None
    description_length: int | None = None
    description_px_est: int | None = None  # تخمین پهنای پیکسلی در SERP (فونت فارسی پهن‌تر است)
    lang_declared: str | None = None
    lang_source: str | None = None
    lang_detected: str | None = None
    lang_scores: dict[str, float] = Field(default_factory=dict)
    open_graph: dict[str, str] = Field(default_factory=dict)
    twitter: dict[str, str] = Field(default_factory=dict)
    json_ld: list[Any] = Field(default_factory=list)
    json_ld_types: list[str] = Field(default_factory=list)
    author: str | None = None
    author_source: str | None = None
    published_at: str | None = None
    published_at_raw: str | None = None
    published_at_source: str | None = None
    modified_at: str | None = None
    modified_at_raw: str | None = None


class Block(_Base):
    type: BlockType
    text: str
    html: str
    xpath: str
    votes: int = 1


class Chunk(_Base):
    id: str
    index: int
    heading_path: list[str] = Field(default_factory=list)
    text: str
    text_raw: str
    embed_text: str
    word_count: int
    sentence_count: int = 0
    block_types: list[str] = Field(default_factory=list)
    xpath_start: str | None = None
    xpath_end: str | None = None
    position: float = 0.0
    overlap_words: int = 0


class Content(_Base):
    text: str | None = None
    text_raw: str | None = None
    html: str | None = None
    markdown: str | None = None
    blocks: list[Block] = Field(default_factory=list)
    chunks: list[Chunk] = Field(default_factory=list)
    word_count: int | None = None
    char_count: int | None = None
    reading_time_min: int | None = None
    confidence: float | None = None
    low_confidence: bool = False
    extractors: dict[str, float] = Field(default_factory=dict)


class Heading(_Base):
    level: int
    text: str
    in_main: bool = False


class Link(_Base):
    url: str
    anchor: str | None = None
    rel: str | None = None
    internal: bool = False
    nofollow: bool = False
    in_main: bool = False


class Image(_Base):
    src: str
    alt: str | None = None
    width: int | None = None
    height: int | None = None
    in_main: bool = False


class LinksSummary(_Base):
    internal: int = 0
    external: int = 0
    nofollow: int = 0
    in_main: int = 0


class ImagesSummary(_Base):
    total: int = 0
    missing_alt: int = 0


class Structure(_Base):
    headings: list[Heading] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    images: list[Image] = Field(default_factory=list)
    links_summary: LinksSummary = Field(default_factory=LinksSummary)
    images_summary: ImagesSummary = Field(default_factory=ImagesSummary)


class PageRecord(_Base):
    schema_version: str = SCHEMA_VERSION
    url: str
    final_url: str | None = None
    canonical: str | None = None
    fetched_at: datetime | None = None
    http: HttpInfo = Field(default_factory=HttpInfo)
    seo: SeoMeta = Field(default_factory=SeoMeta)
    content: Content = Field(default_factory=Content)
    structure: Structure = Field(default_factory=Structure)
    content_hash: str | None = None
    raw_html_ref: str | None = None
    llm: dict[str, Any] | None = None  # خروجی لایه اختیاری LLM (schema-محور)؛ خارج از مسیر اصلی
    error: str | None = None


class RunStats(_Base):
    """آمار یک اجرا — در `run.json` ذخیره می‌شود."""

    run_id: str
    tool_version: str
    started_at: datetime
    finished_at: datetime | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    n: int = 0
    ok: int = 0
    failed: int = 0
    rendered: int = 0
    skipped_unchanged: int = 0
    robots_blocked: int = 0
    p50_ms: float | None = None
    p95_ms: float | None = None
