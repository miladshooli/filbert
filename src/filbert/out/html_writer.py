"""خروجی HTML تمیز: `content.html` در یک پوسته حداقلی بدون CSS/JS."""

from __future__ import annotations

from filbert.extract.cleanhtml import build_document
from filbert.models import PageRecord
from filbert.out.common import direction_for, page_lang


def render(record: PageRecord) -> str:
    lang = page_lang(record)
    return build_document(
        record.content.html or f'<article lang="{lang}" dir="{direction_for(lang)}"></article>',
        title=record.seo.title,
        source_url=record.final_url or record.url,
        fetched_at=record.fetched_at.isoformat(timespec="seconds") if record.fetched_at else None,
        lang=lang,
        direction=direction_for(lang),
    )
