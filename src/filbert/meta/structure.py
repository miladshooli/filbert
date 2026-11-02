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
    headings: list[tuple[int, Heading]] = field(default_factory=list)
    links: list[tuple[int, Link]] = field(default_factory=list)
    images: list[tuple[int, Image]] = field(default_factory=list)


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
                draft.headings.append((n.mem_id, Heading(level=int(tag[1]), text=text)))
        elif tag == "a" and len(draft.links) < max_links:
            href = (n.attributes.get("href") or "").strip()
            if not href or href.lower().startswith(_SKIP_HREF):
                continue
            url = normalize_url(href, base=page_url)
            if not url.startswith(("http://", "https://")):
                continue
            rel = (n.attributes.get("rel") or "").strip() or None
            tokens = {t.lower() for t in rel.split()} if rel else set()
            anchor = " ".join(node_text(n).split()) or None
            if anchor is None:
                img = n.css_first("img")
                if img is not None and img.attributes.get("alt"):
                    anchor = " ".join(img.attributes["alt"].split()) or None
            draft.links.append(
                (
                    n.mem_id,
                    Link(
                        url=url,
                        anchor=anchor,
                        rel=rel,
                        internal=is_internal(url, page_url),
                        nofollow="nofollow" in tokens,
                    ),
                )
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
                    Image(
                        src=src,
                        alt=(" ".join(alt.split()) if alt is not None else None),
                        width=_int_attr(a.get("width")),
                        height=_int_attr(a.get("height")),
                    ),
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
    headings = [h.model_copy(update={"in_main": mid in ids}) for mid, h in draft.headings]
    links = [ln.model_copy(update={"in_main": mid in ids}) for mid, ln in draft.links]
    images = [im.model_copy(update={"in_main": mid in ids}) for mid, im in draft.images]
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
