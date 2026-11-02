"""استخراج ساختاریافته با Claude (الگوی lightfeed): Markdown تمیز + schema → JSON معتبر.

- SDK رسمی `anthropic`؛ `client.messages.parse(..., output_format=Schema)` خروجی را به pydantic می‌دهد.
- system prompt ثابت با prompt caching؛ کش پاسخ روی دیسک (کلید: مدل + schema + hash متن).
- پیش‌فرض مدل `claude-opus-5-5`؛ thinking پیش‌فرض (adaptive) و `effort` قابل تنظیم.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

log = logging.getLogger(__name__)
DEFAULT_MODEL = "claude-opus-5-5"
MAX_INPUT_CHARS = 60_000  # ~۱۵ هزار توکن فارسی؛ بیشتر از این Markdown بریده می‌شود (با اعلام)

SYSTEM = (
    "You extract structured data from Persian (Farsi) web content. The user message contains the page's main "
    "content as Markdown. Fill the requested schema strictly from the content: never invent facts, keep Persian "
    "text in Persian with correct ZWNJ (U+200C) usage, keep numbers as written. If a field is not supported by the "
    "content, use an empty string, empty list or false as appropriate."
)


class LLMUnavailable(RuntimeError):
    pass


class LLMExtractor:
    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = "medium",
        max_tokens: int = 8000,
        cache_dir: Path | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.cache_dir = Path(cache_dir) / "llm" if cache_dir else None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = client
        self.stats = {"calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0}

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:  # pragma: no cover
                raise LLMUnavailable("install extras: uv sync --extra llm (anthropic SDK)") from e
            self._client = anthropic.Anthropic()  # ANTHROPIC_API_KEY یا پروفایل `ant auth login`
        return self._client

    def _cache_key(self, text: str, schema: type[BaseModel], instructions: str | None) -> str:
        h = hashlib.sha256()
        for part in (
            self.model,
            schema.__name__,
            json.dumps(schema.model_json_schema(), sort_keys=True),
            instructions or "",
            text,
        ):
            h.update(part.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def extract(
        self,
        markdown: str,
        schema: type[BaseModel],
        *,
        instructions: str | None = None,
        url: str | None = None,
    ) -> BaseModel:
        text = markdown
        if len(text) > MAX_INPUT_CHARS:
            log.warning(
                "llm: input truncated from %d to %d chars (%s)", len(text), MAX_INPUT_CHARS, url
            )
            text = text[:MAX_INPUT_CHARS]
        key = self._cache_key(text, schema, instructions)
        if self.cache_dir is not None:
            hit = self.cache_dir / f"{key}.json"
            if hit.exists():
                self.stats["cache_hits"] += 1
                return schema.model_validate_json(hit.read_text(encoding="utf-8"))
        user = (
            ((instructions.strip() + "\n\n") if instructions else "")
            + (f"URL: {url}\n\n" if url else "")
            + "<content>\n"
            + text
            + "\n</content>"
        )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        self.stats["calls"] += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.stats["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
            self.stats["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            raise LLMUnavailable(f"model refused: {getattr(details, 'category', None)}")
        parsed = response.parsed_output
        if parsed is None:
            raise LLMUnavailable(
                "no parsed output (stop_reason=%s)" % getattr(response, "stop_reason", None)
            )
        if self.cache_dir is not None:
            (self.cache_dir / f"{key}.json").write_text(parsed.model_dump_json(), encoding="utf-8")
        return parsed
