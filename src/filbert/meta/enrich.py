"""تکمیل `SeoMeta` با JSON-LD، OG/Twitter، نویسنده، تاریخ‌ها، طول‌ها و زبان (فاز ۳).

`enrich_head()` روی درخت کامل (پیش از preclean) و `finish()` پس از استخراج متن اصلی.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from filbert.extract.domtext import Tree, class_id, node_text
from filbert.fa.lang import detect
from filbert.meta import jsonld
from filbert.meta.dates import ParsedDate, parse_any, parse_text
from filbert.meta.social import extract_author, extract_social
from filbert.models import SeoMeta

_DATE_CLASS_RE = re.compile(r"date|time|tarikh|publish|entesh|zaman|clock|posted", re.IGNORECASE)
_PX = {"arabic": 7.2, "upper": 8.5, "lower": 6.3, "digit": 7.0, "space": 3.0, "other": 5.0}
_ARABIC_RANGE = (0x0600, 0x06FF)


@dataclass(slots=True)
class DateCandidates:
    """مقادیر خام تاریخ به ترتیب اولویت زنجیره (پیش از preclean جمع می‌شوند)."""

    published: list[tuple[str, str]] = field(default_factory=list)  # (source, raw)
    modified: list[tuple[str, str]] = field(default_factory=list)


def px_estimate(text: str | None) -> int | None:
    if not text:
        return None
    total = 0.0
    for ch in text:
        o = ord(ch)
        if _ARABIC_RANGE[0] <= o <= _ARABIC_RANGE[1]:
            total += _PX["arabic"]
        elif ch.isdigit():
            total += _PX["digit"]
        elif ch.isspace():
            total += _PX["space"]
        elif ch.isupper():
            total += _PX["upper"]
        elif ch.isalpha():
            total += _PX["lower"]
        else:
            total += _PX["other"]
    return int(total)


def collect_date_candidates(
    tree: Tree, og: dict[str, str], items: list[dict[str, Any]]
) -> DateCandidates:
    c = DateCandidates()
    for k in ("article:published_time", "og:published_time", "article:published"):
        if og.get(k):
            c.published.append(("article_published_time", og[k]))
    for k in ("article:modified_time", "og:updated_time", "article:modified"):
        if og.get(k):
            c.modified.append(("article_modified_time", og[k]))
    dp, dm = jsonld.date_published(items), jsonld.date_modified(items)
    if dp:
        c.published.append(("json_ld", dp))
    if dm:
        c.modified.append(("json_ld", dm))
    for t in tree.css("time[datetime]"):
        dt = (t.attributes.get("datetime") or "").strip()
        if not dt:
            continue
        prop = ((t.attributes.get("itemprop") or "") + " " + class_id(t)).lower()
        if "modified" in prop or "update" in prop:
            c.modified.append(("time_element", dt))
        else:
            c.published.append(("time_element", dt))
    for sel in (
        'meta[name="date"]',
        'meta[name="pubdate"]',
        'meta[name="publish_date"]',
        'meta[itemprop="datePublished"]',
        'meta[property="datePublished"]',
    ):
        for m in tree.css(sel):
            v = (m.attributes.get("content") or "").strip()
            if v:
                c.published.append(("meta_date", v))
    for m in tree.css('meta[itemprop="dateModified"], meta[name="last-modified"]'):
        v = (m.attributes.get("content") or "").strip()
        if v:
            c.modified.append(("meta_date", v))
    # عناصر با class تاریخ (متن): فقط کوتاه‌ها
    body = tree.body
    if body is not None:
        n_found = 0
        for n in body.traverse():
            if not n.is_element_node or n.tag in ("script", "style"):
                continue
            cid = class_id(n)
            if cid and _DATE_CLASS_RE.search(cid):
                text = node_text(n)
                if 4 <= len(text) <= 60:
                    c.published.append(("date_class", text))
                    n_found += 1
                    if n_found >= 5:
                        break
    return c


def _first_parsed(cands: list[tuple[str, str]]) -> ParsedDate | None:
    for source, raw in cands:
        p = parse_any(raw, source=source)
        if p:
            return p
    return None


def enrich_head(seo: SeoMeta, tree: Tree, base_url: str) -> tuple[SeoMeta, DateCandidates]:
    """JSON-LD، OG/Twitter، نویسنده، کلیدواژه از JSON-LD، طول‌ها. درخت کامل، پیش از preclean."""
    items = jsonld.extract_jsonld(tree)
    og, tw = extract_social(tree, base_url)
    author, author_source = extract_author(tree, items)
    seo.json_ld = items
    seo.json_ld_types = jsonld.types_of(items)
    seo.open_graph = og
    seo.twitter = tw
    seo.author, seo.author_source = author, author_source
    if not seo.keywords:
        kw = jsonld.keywords(items)
        if kw:
            seo.keywords, seo.keywords_source = kw, "json_ld"
    seo.title_length = len(seo.title) if seo.title else None
    seo.description_length = len(seo.description) if seo.description else None
    seo.description_px_est = px_estimate(seo.description)
    return seo, collect_date_candidates(tree, og, items)


def finish(
    seo: SeoMeta, cands: DateCandidates, main_text: str | None, fallback_text: str | None
) -> SeoMeta:
    """تاریخ‌ها (با fallback regex روی ابتدای متن اصلی) و تشخیص زبان؛ پس از استخراج."""
    pub = _first_parsed(cands.published)
    if pub is None and main_text:
        pub = parse_text(main_text[:800], source="text")
    if pub:
        seo.published_at, seo.published_at_raw, seo.published_at_source = (
            pub.iso,
            pub.raw,
            pub.source,
        )
    mod = _first_parsed(cands.modified)
    if mod:
        seo.modified_at, seo.modified_at_raw = mod.iso, mod.raw
    lang = detect(main_text or fallback_text)
    seo.lang_detected = lang.lang
    seo.lang_scores = lang.scores
    return seo
