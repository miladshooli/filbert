"""خروجی Markdown: front-matter YAML + بدنه تبدیل‌شده از HTML تمیز (بلوک به بلوک).

قواعد: هدینگ ATX با سطح اصلی، جدول → pipe table (اگر سلولی چندخطی بود، HTML خام جدول می‌ماند)،
تصویر `![alt](src)`، لینک‌ها مطلق (از cleanhtml). ZWNJ حفظ می‌شود.
"""

from __future__ import annotations

import re

import yaml
from markdownify import MarkdownConverter

from filbert.models import Block, PageRecord
from filbert.out.common import direction_for, page_lang

_MULTILINE_CELL_RE = re.compile(r"<(?:br|p|ul|ol|div|pre)\b", re.IGNORECASE)
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")
_converter = MarkdownConverter(heading_style="ATX", bullets="-", strip=None, escape_misc=False)


def block_to_markdown(block: Block) -> str:
    if block.type == "table" and _MULTILINE_CELL_RE.search(block.html[len("<table") :]):
        return block.html  # جدول چندخطی: HTML خام داخل MD
    return _converter.convert(block.html).strip()


def front_matter(record: PageRecord) -> str:
    lang = page_lang(record)
    data = {
        "title": record.seo.title,
        "url": record.final_url or record.url,
        "canonical": record.canonical,
        "description": record.seo.description,
        "published_at": record.seo.published_at,
        "lang": lang,
        "dir": direction_for(lang),
        "word_count": record.content.word_count,
        "confidence": record.content.confidence,
        "fetched_at": record.fetched_at.isoformat(timespec="seconds") if record.fetched_at else None,
    }
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return f"---\n{body}---\n"


def render_body(record: PageRecord) -> str:
    parts = [block_to_markdown(b) for b in record.content.blocks]
    text = "\n\n".join(p for p in parts if p)
    return _TRAILING_WS_RE.sub("\n", text).strip() + "\n"


def render(record: PageRecord) -> str:
    return front_matter(record) + "\n" + render_body(record)
