"""Open Graph / Twitter Card و نویسنده.

- `open_graph`: همه `og:*` و `article:*` (URLها مطلق)؛ `twitter`: همه `twitter:*`.
- نویسنده: `meta[name=author]` → JSON-LD `author.name` → `a[rel=author]` → عنصر با class/id `author|byline|…`.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from filbert.extract.domtext import Tree, class_id, node_text
from filbert.meta import jsonld
from filbert.meta.dates import parse_text
from filbert.meta.head import collect_meta

_URL_KEYS = {
    "og:image",
    "og:url",
    "og:audio",
    "og:video",
    "twitter:image",
    "twitter:url",
    "og:image:url",
    "og:image:secure_url",
}
_AUTHOR_CLASS_RE = re.compile(
    r"author|byline|writer|reporter|nevisande|nevisandeh|khabarnegar", re.IGNORECASE
)
_AUTHOR_PREFIX_RE = re.compile(
    r"^\s*(?:نویسنده|نوشته(?:‌|\s)?(?:شده)?(?:\s+توسط)?|توسط|گزارش(?:گر)?|خبرنگار|by|author|written by)\s*[:：\-–]?\s*",
    re.IGNORECASE,
)
_MAX_AUTHOR_LEN = 80


def extract_social(tree: Tree, base_url: str) -> tuple[dict[str, str], dict[str, str]]:
    by_name, by_prop, _multi = collect_meta(tree)
    og: dict[str, str] = {}
    tw: dict[str, str] = {}
    for k, v in by_prop.items():
        if k.startswith(("og:", "article:", "book:", "profile:")):
            og[k] = urljoin(base_url, v) if k in _URL_KEYS else v
        elif k.startswith("twitter:"):
            tw[k] = urljoin(base_url, v) if k in _URL_KEYS else v
    for k, v in by_name.items():
        if k.startswith("twitter:") and k not in tw:
            tw[k] = urljoin(base_url, v) if k in _URL_KEYS else v
    return og, tw


_AUTHOR_SPLIT_RE = re.compile(r"\s*(?:\||•|·|/|،|,|\s-\s|\s–\s|\sدر\s|\sat\s|\son\s)\s*")


def clean_author(raw: str | None) -> str | None:
    if not raw:
        return None
    s = " ".join(raw.split())
    s = _AUTHOR_PREFIX_RE.sub("", s)
    d = parse_text(s)
    if d:
        s = s[: s.find(d.raw)] if d.raw in s else s  # تاریخ کنار نام نویسنده
    s = _AUTHOR_SPLIT_RE.split(s, maxsplit=1)[0].strip(" :-–|،,")
    if not s or len(s) > _MAX_AUTHOR_LEN or s.lower().startswith(("http", "www.")):
        return None
    return s


def extract_author(tree: Tree, jsonld_items: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """(نویسنده، منبع). منبع یکی از: meta, json_ld, rel_author, class."""
    by_name, _by_prop, _multi = collect_meta(tree)
    a = clean_author(by_name.get("author"))
    if a:
        return a, "meta"
    a = clean_author(jsonld.author_name(jsonld_items))
    if a:
        return a, "json_ld"
    for link in tree.css('a[rel~="author"]'):
        a = clean_author(node_text(link))
        if a:
            return a, "rel_author"
    body = tree.body
    if body is not None:
        for n in body.traverse():
            if not n.is_element_node or n.tag in ("script", "style", "a", "img"):
                continue
            cid = class_id(n)
            if cid and _AUTHOR_CLASS_RE.search(cid):
                text = node_text(n)
                if 0 < len(text) <= _MAX_AUTHOR_LEN:
                    a = clean_author(text.split("\n")[0])
                    if a:
                        return a, "class"
    return None, None
