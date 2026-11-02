"""ساختار صفحه: هدینگ‌ها، لینک‌ها و تصاویر — از درخت کامل **پیش از preclean**؛ `in_main` پس از استخراج.

`collect()` نودها و `mem_id`شان را نگه می‌دارد؛ `finalize()` با نودهای بلوک‌های برنده، `in_main` را پر می‌کند
(نودهایی که preclean حذف کرده، در درخت نیستند و طبعاً `in_main=false` می‌مانند).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from filbert.extract.blocks import HEADING_TAGS
from filbert.extract.cleanhtml import img_src
from filbert.extract.domtext import Node, Tree, node_text
from filbert.fetch.urlnorm import is_internal, normalize_url
from filbert.models import Heading, Image, ImagesSummary, Link, LinksSummary, Structure

_SKIP_HREF = ("#", "javascript:", "mailto:", "tel:", "sms:", "data:")
_INT_RE = re.compile(r"^\s*(\d{1,5})")


@dataclass(slots=True)
class StructureDraft:
    """نسخه سبک (tuple) تا مدل‌های pydantic فقط یک بار در `finalize` ساخته شوند."""

    headings: list[tuple[int, int, str]] = field(default_factory=list)  # mem_id, level, text
    links: list[tuple[int, str, str | None, str | None, bool, bool]] = field(default_factory=list)
    images: list[tuple[int, str, str | None, int | None, int | None]] = field(default_factory=list)


def _int_attr(v: str | None) -> int | None:
    if not v:
        return None
    m = _INT_RE.match(v)
    return int(m.group(1)) if m else None


def collect(
    tree: Tree, page_url: str, *, max_links: int = 2000, max_images: int = 500
) -> StructureDraft:
    draft = StructureDraft()
    body = tree.body
    if body is None:
        return draft
    for n in body.traverse():
        if not n.is_element_node:
            continue
        tag = n.tag
        if tag in HEADING_TAGS:
            text = " ".join(node_text(n).split())
            if text:
                draft.headings.append((n.mem_id, int(tag[1]), text))
        elif tag == "a" and len(draft.links) < max_links:
            href = (n.attributes.get("href") or "").strip()
            if not href or href.lower().startswith(_SKIP_HREF):
                continue
            url = normalize_url(href, base=page_url)
            if not url.startswith(("http://", "https://")):
                continue
            rel = (n.attributes.get("rel") or "").strip() or None
            tokens = {t.lower() for t in rel.split()} if rel else set()
            anchor = " ".join(n.text(deep=True).split()) or None
            if anchor is None:
                img = n.css_first("img")
                if img is not None and img.attributes.get("alt"):
                    anchor = " ".join(img.attributes["alt"].split()) or None
            draft.links.append(
                (n.mem_id, url, anchor, rel, is_internal(url, page_url), "nofollow" in tokens)
            )
        elif tag == "img" and len(draft.images) < max_images:
            src = img_src(n.attributes, page_url)
            if not src or not src.startswith(("http://", "https://")):
                continue
            a = n.attributes
            alt = a.get("alt")
            draft.images.append(
                (
                    n.mem_id,
                    src,
                    (" ".join(alt.split()) if alt is not None else None),
                    _int_attr(a.get("width")),
                    _int_attr(a.get("height")),
                )
            )
    return draft


def main_ids(main_nodes: list[Node]) -> set[int]:
    ids: set[int] = set()
    for node in main_nodes:
        ids.add(node.mem_id)
        for d in node.traverse():
            if d.is_element_node:
                ids.add(d.mem_id)
    return ids


def finalize(draft: StructureDraft, main_nodes: list[Node]) -> Structure:
    ids = main_ids(main_nodes)
    headings = [Heading(level=lvl, text=t, in_main=mid in ids) for mid, lvl, t in draft.headings]
    links = [
        Link(url=u, anchor=a, rel=r, internal=i, nofollow=nf, in_main=mid in ids)
        for mid, u, a, r, i, nf in draft.links
    ]
    images = [
        Image(src=src, alt=alt, width=w, height=h, in_main=mid in ids)
        for mid, src, alt, w, h in draft.images
    ]
    return Structure(
        headings=headings,
        links=links,
        images=images,
        links_summary=LinksSummary(
            internal=sum(1 for ln in links if ln.internal),
            external=sum(1 for ln in links if not ln.internal),
            nofollow=sum(1 for ln in links if ln.nofollow),
            in_main=sum(1 for ln in links if ln.in_main),
        ),
        images_summary=ImagesSummary(
            total=len(images), missing_alt=sum(1 for im in images if not im.alt)
        ),
    )
