"""مدل‌های ورودی API (pydantic)؛ همین‌ها مستندات OpenAPI در `/docs` را می‌سازند."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RenderMode = Literal["never", "auto", "always"]


class Options(BaseModel):
    """تنظیمات قابل‌تغییر در هر درخواست؛ بقیه از تنظیمات سرور (`FILBERT_*`) می‌آیند."""

    model_config = ConfigDict(extra="forbid")

    render: RenderMode | None = Field(
        default=None, description="never | auto | always (needs the server's render extra)"
    )
    digits: Literal["fa", "en"] | None = Field(
        default=None, description="digits in normalized text"
    )
    recall: bool | None = Field(default=None, description="union of the three extractors")
    chunk: bool | None = Field(default=None, description="build embedding chunks")
    chunk_max_words: int | None = Field(default=None, ge=20, le=2000)
    chunk_overlap_sentences: int | None = Field(default=None, ge=0, le=5)
    force: bool = Field(default=False, description="ignore the cache and ETag; download again")

    def overrides(self) -> dict[str, Any]:
        keys = ("render", "digits", "recall", "chunk", "chunk_max_words", "chunk_overlap_sentences")
        return {k: getattr(self, k) for k in keys if getattr(self, k) is not None}


class ExtractRequest(Options):
    url: str | None = Field(default=None, description="page to fetch, or base URL for `html`")
    html: str | None = Field(default=None, description="raw HTML; no fetch when given")
    fields: list[str] | None = Field(
        default=None,
        description='keep only these paths, e.g. ["seo.title", "content.text", "content.chunks"]',
        examples=[["seo", "content.text", "content.chunks"]],
    )

    @model_validator(mode="after")
    def _source(self) -> ExtractRequest:
        if not self.url and self.html is None:
            raise ValueError("either `url` or `html` is required")
        return self


class BatchRequest(Options):
    urls: list[str] = Field(min_length=1, description="pages to fetch and extract")
    fields: list[str] | None = None


class JobRequest(Options):
    urls: list[str] = Field(default_factory=list)
    sitemap: str | None = Field(default=None, description="sitemap or sitemap index URL")
    limit: int = Field(default=1000, ge=1, description="max URLs (capped by the server)")
    pattern: str | None = Field(default=None, max_length=300, description="regex to include")
    exclude: str | None = Field(default=None, max_length=300, description="regex to exclude")
    only_changed: bool = Field(
        default=False, description="skip pages whose content_hash did not change"
    )

    @field_validator("pattern", "exclude")
    @classmethod
    def _regex(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"invalid regex: {e}") from e
        return v

    @model_validator(mode="after")
    def _source(self) -> JobRequest:
        if not self.urls and not self.sitemap:
            raise ValueError("either `urls` or `sitemap` is required")
        return self


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    url: str | None = None
    html: str | None = None
    schema_name: Literal["article", "seo"] = Field(default="article", alias="schema")
    instructions: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _source(self) -> LLMRequest:
        if not self.url and self.html is None:
            raise ValueError("either `url` or `html` is required")
        return self
