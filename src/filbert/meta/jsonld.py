"""JSON-LD: پارس همه `script[type=application/ld+json]` با orjson و تحمل خطا.

خروجی: فهرست اشیاء (آرایه و `@graph` باز می‌شوند)، فهرست `@type`ها، و کمکی‌های استخراج فیلد.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from typing import Any

import orjson

from filbert.extract.domtext import Tree

log = logging.getLogger(__name__)
_CDATA_RE = re.compile(r"^\s*(?://)?\s*<!\[CDATA\[(.*?)\]\]>\s*$", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _loads_tolerant(raw: str) -> Any | None:
    text = raw.strip()
    m = _CDATA_RE.match(text)
    if m:
        text = m.group(1).strip()
    if not text:
        return None
    for candidate in (text, _TRAILING_COMMA_RE.sub(r"\1", _CTRL_RE.sub("", text))):
        try:
            return orjson.loads(candidate)
        except orjson.JSONDecodeError:
            continue
    # چند شیء پشت سر هم یا متن اضافه: اولین شیء/آرایه کامل را بردار
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start >= 0:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    try:
                        return orjson.loads(text[start : i + 1])
                    except orjson.JSONDecodeError:
                        return None
    return None


def _flatten(obj: Any) -> Iterator[dict[str, Any]]:
    if isinstance(obj, list):
        for item in obj:
            yield from _flatten(item)
    elif isinstance(obj, dict):
        if "@graph" in obj and isinstance(obj["@graph"], list):
            yield from _flatten(obj["@graph"])
            rest = {k: v for k, v in obj.items() if k != "@graph"}
            if "@type" in rest:
                yield rest
        else:
            yield obj


def extract_jsonld(tree: Tree) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for script in tree.css("script"):
        t = (script.attributes.get("type") or "").strip().lower()
        if t != "application/ld+json":
            continue
        data = _loads_tolerant(script.text(deep=True))
        if data is None:
            log.debug("unparsable JSON-LD block")
            continue
        out.extend(_flatten(data))
    return out


def types_of(items: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for it in items:
        t = it.get("@type")
        for name in t if isinstance(t, list) else [t]:
            if isinstance(name, str) and name not in seen:
                seen.append(name)
    return seen


def _as_text(v: Any) -> str | None:
    if isinstance(v, str):
        s = " ".join(v.split()).strip()
        return s or None
    if isinstance(v, dict):
        for k in ("name", "@value", "headline"):
            if k in v:
                return _as_text(v[k])
    if isinstance(v, list):
        for x in v:
            t = _as_text(x)
            if t:
                return t
    return None


_CONTENT_TYPES = (
    "NewsArticle",
    "Article",
    "BlogPosting",
    "TechArticle",
    "Report",
    "ScholarlyArticle",
    "Product",
    "WebPage",
    "DiscussionForumPosting",
    "QAPage",
    "Recipe",
    "VideoObject",
)


def _ranked(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """اشیاء محتوایی (Article…) جلوتر از بقیه (Organization, BreadcrumbList…)."""

    def rank(it: dict[str, Any]) -> int:
        t = it.get("@type")
        names = t if isinstance(t, list) else [t]
        for i, ct in enumerate(_CONTENT_TYPES):
            if ct in names:
                return i
        return len(_CONTENT_TYPES)

    return sorted(items, key=rank)


def first_field(items: list[dict[str, Any]], *keys: str) -> str | None:
    for it in _ranked(items):
        for k in keys:
            if k in it:
                t = _as_text(it[k])
                if t:
                    return t
    return None


def author_name(items: list[dict[str, Any]]) -> str | None:
    return first_field(items, "author", "creator")


def date_published(items: list[dict[str, Any]]) -> str | None:
    return first_field(items, "datePublished", "dateCreated", "uploadDate")


def date_modified(items: list[dict[str, Any]]) -> str | None:
    return first_field(items, "dateModified")


def headline(items: list[dict[str, Any]]) -> str | None:
    return first_field(items, "headline", "name")


def keywords(items: list[dict[str, Any]]) -> list[str] | None:
    for it in _ranked(items):
        kw = it.get("keywords")
        if isinstance(kw, list):
            vals = [_as_text(x) for x in kw]
            out = [v for v in vals if v]
            if out:
                return out
        if isinstance(kw, str):
            parts = [p.strip() for p in re.split(r"[،,;]", kw) if p.strip()]
            if parts:
                return parts
    return None
