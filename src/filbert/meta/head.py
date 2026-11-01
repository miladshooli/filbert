"""متادیتای `<head>` — فاز ۱: title/description/keywords/canonical/robots/lang با زنجیره اولویت.

هر فیلد `*_source` دارد تا در ممیزی معلوم باشد مقدار از کجا آمده. مقادیر فقط strip و فشرده‌سازی
فاصله می‌شوند؛ **هیچ نرمال‌سازی فارسی** روی متادیتا اعمال نمی‌شود (باید همان چیزی باشد که گوگل می‌بیند).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from filbert.extract.domtext import Tree, node_text
from filbert.fetch.urlnorm import normalize_url
from filbert.models import Hreflang, Robots, SeoMeta

_WS_RE = re.compile(r"\s+")
_KEYWORD_SPLIT_RE = re.compile(r"[،,;؛]")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    v = _WS_RE.sub(" ", value).strip()
    return v or None


def _collect_meta(tree: Tree) -> tuple[dict[str, str], dict[str, str], dict[str, list[str]]]:
    """meta[name] (کوچک‌شده) → content؛ meta[property] → content؛ همه مقادیر چندتایی."""
    by_name: dict[str, str] = {}
    by_prop: dict[str, str] = {}
    multi: dict[str, list[str]] = {}
    for m in tree.css("meta"):
        a = m.attributes
        content = _clean(a.get("content"))
        if content is None:
            continue
        name = (a.get("name") or "").strip().lower()
        prop = (a.get("property") or "").strip().lower()
        if name:
            by_name.setdefault(name, content)
            multi.setdefault(name, []).append(content)
        if prop:
            by_prop.setdefault(prop, content)
            multi.setdefault(prop, []).append(content)
    return by_name, by_prop, multi


def _first(*pairs: tuple[str, str | None]) -> tuple[str | None, str | None]:
    for source, value in pairs:
        if value:
            return value, source
    return None, None


def _lang_from_locale(locale: str | None) -> str | None:
    if not locale:
        return None
    return locale.replace("-", "_").split("_")[0].lower() or None


def parse_robots(*values: str | None) -> Robots:
    raws = [v for v in values if v]
    if not raws:
        return Robots()
    tokens = {t.strip().lower() for raw in raws for t in raw.split(",")}
    return Robots(
        raw=", ".join(raws),
        noindex="noindex" in tokens or "none" in tokens,
        nofollow="nofollow" in tokens or "none" in tokens,
    )


def split_keywords(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [p.strip() for p in _KEYWORD_SPLIT_RE.split(value)]
    out = [p for p in parts if p]
    return out or None


def extract_head(
    tree: Tree, base_url: str, response_headers: Mapping[str, str] | None = None
) -> SeoMeta:
    """از درخت کامل (قبل از preclean) متادیتای head را می‌خواند."""
    by_name, by_prop, multi = _collect_meta(tree)
    headers = {k.lower(): v for k, v in (response_headers or {}).items()}

    title_node = tree.css_first("title")
    title_tag = _clean(title_node.text(deep=True)) if title_node is not None else None
    og_title = by_prop.get("og:title")
    h1_node = tree.css_first("h1")
    h1 = _clean(node_text(h1_node)) if h1_node is not None else None
    title, title_source = _first(
        ("title_tag", title_tag),
        ("og_title", og_title),
        ("twitter_title", by_name.get("twitter:title") or by_prop.get("twitter:title")),
        ("h1", h1),
    )

    description, description_source = _first(
        ("meta", by_name.get("description")),
        ("og_description", by_prop.get("og:description")),
        (
            "twitter_description",
            by_name.get("twitter:description") or by_prop.get("twitter:description"),
        ),
    )

    keywords, keywords_source = split_keywords(by_name.get("keywords")), "meta"
    if not keywords:
        tags = multi.get("article:tag")
        keywords, keywords_source = (tags or None), ("article_tag" if tags else None)

    canonical_node = tree.css_first('link[rel="canonical"]')
    canonical_raw = (
        _clean(canonical_node.attributes.get("href")) if canonical_node is not None else None
    )
    canonical, canonical_source = _first(
        ("link_canonical", canonical_raw), ("og_url", by_prop.get("og:url"))
    )
    if canonical:
        canonical = normalize_url(canonical, base=base_url)

    robots = parse_robots(
        by_name.get("robots"), by_name.get("googlebot"), headers.get("x-robots-tag")
    )

    hreflang: list[Hreflang] = []
    for link in tree.css('link[rel="alternate"]'):
        a = link.attributes
        hl, href = _clean(a.get("hreflang")), _clean(a.get("href"))
        if hl and href:
            hreflang.append(Hreflang(lang=hl, url=normalize_url(href, base=base_url)))

    html_node = tree.css_first("html")
    html_lang = _clean(html_node.attributes.get("lang")) if html_node is not None else None
    lang_declared, lang_source = _first(
        ("html_lang", _lang_from_locale(html_lang)),
        ("og_locale", _lang_from_locale(by_prop.get("og:locale"))),
    )

    open_graph = {k: v for k, v in by_prop.items() if k.startswith(("og:", "article:"))}
    twitter = {k: v for k, v in {**by_prop, **by_name}.items() if k.startswith("twitter:")}

    return SeoMeta(
        title=title,
        title_source=title_source,
        title_tag=title_tag,
        og_title=og_title,
        h1=h1,
        description=description,
        description_source=description_source,
        keywords=keywords,
        keywords_source=keywords_source if keywords else None,
        canonical=canonical,
        canonical_source=canonical_source,
        robots=robots,
        hreflang=hreflang,
        lang_declared=lang_declared,
        lang_source=lang_source,
        open_graph=open_graph,
        twitter=twitter,
    )
