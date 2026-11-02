"""تولید Markdown مستقیم از نودهای selectolax (همان پیمایش cleanhtml؛ بدون markdownify در مسیر اصلی).

قواعد BLUEPRINT: هدینگ ATX با سطح اصلی، جدول → pipe table (سلول چندخطی → HTML خام جدول)،
تصویر `![alt](src)`، لینک‌های مطلق، ZWNJ حفظ می‌شود.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from filbert.extract.cleanhtml import DROP_TAGS, img_src, sanitize_node
from filbert.extract.domtext import BLOCK_TAGS, Node

_WS_RE = re.compile(r"[ \t\r\f\v\u00a0]+")
_INLINE_BLOCKS = frozenset(
    {"p", "div", "section", "article", "li", "td", "th", "figcaption", "summary", "details"}
)
_MD_ESCAPE_RE = re.compile(r"(?<!\\)([*_`\[\]])")


def _esc(text: str) -> str:
    return _MD_ESCAPE_RE.sub(r"\\\1", text)


def _href(node: Node, base_url: str | None) -> str | None:
    v = (node.attributes.get("href") or "").strip()
    if not v or v.lower().startswith(("javascript:", "data:")):
        return None
    return urljoin(base_url, v) if base_url else v


def inline(node: Node, base_url: str | None) -> str:
    """محتوای inline یک عنصر (بدون تگ ریشه)؛ بلوک‌های داخلی با خط جدید جدا می‌شوند."""
    parts: list[str] = []
    for child in node.iter(include_text=True):
        tag = child.tag
        if tag == "-text":
            parts.append(_esc(_WS_RE.sub(" ", child.text_content or "")))
        elif not child.is_element_node or tag in DROP_TAGS or "data-md-skip" in child.attributes:
            continue
        elif tag == "br":
            parts.append("\n")
        elif tag in ("strong", "b"):
            s = inline(child, base_url).strip()
            parts.append(f"**{s}**" if s else "")
        elif tag in ("em", "i"):
            s = inline(child, base_url).strip()
            parts.append(f"*{s}*" if s else "")
        elif tag == "code":
            s = _WS_RE.sub(" ", child.text(deep=True)).strip()
            parts.append(f"`{s}`" if s else "")
        elif tag == "a":
            s = inline(child, base_url).strip()
            href = _href(child, base_url)
            parts.append(f"[{s}]({href})" if (s and href) else s)
        elif tag == "img":
            src = img_src(child.attributes, base_url)
            if src:
                parts.append(f"![{_esc((child.attributes.get('alt') or '').strip())}]({src})")
        elif tag in ("ul", "ol"):
            parts.append("\n" + _list(child, base_url, 0) + "\n")
        elif tag in BLOCK_TAGS or tag in _INLINE_BLOCKS:
            parts.append("\n" + inline(child, base_url).strip() + "\n")
        else:
            parts.append(inline(child, base_url))
    text = "".join(parts)
    lines = [ln.strip() for ln in text.split("\n")]
    return "\n".join(
        ln for i, ln in enumerate(lines) if ln or (0 < i < len(lines) - 1 and lines[i - 1])
    )


def _list(node: Node, base_url: str | None, depth: int) -> str:
    ordered = node.tag == "ol"
    out: list[str] = []
    i = 0
    for li in node.iter():
        if not li.is_element_node or li.tag not in ("li", "dd", "dt"):
            continue
        i += 1
        marker = f"{i}. " if ordered else "- "
        # زیرفهرست‌ها جدا رندر می‌شوند
        sub: list[str] = []
        for c in li.iter():
            if c.is_element_node and c.tag in ("ul", "ol"):
                sub.append(_list(c, base_url, depth + 1))
                c_html = c
                c_html.attrs["data-md-skip"] = "1"
        body = (
            inline(_without_sublists(li), base_url)
            .strip()
            .replace("\n", "\n" + " " * (len(marker) + 2 * depth))
        )
        out.append(" " * (2 * depth) + marker + body)
        out.extend(sub)
    return "\n".join(out)


def _without_sublists(li: Node) -> Node:
    # علامت‌گذاری با data-md-skip کافی است؛ inline() آن‌ها را رد می‌کند
    return li


def _table(node: Node, base_url: str | None) -> str:
    rows: list[list[str]] = []
    header: list[str] | None = None
    for tr in node.css("tr"):
        cells = [c for c in tr.iter() if c.is_element_node and c.tag in ("td", "th")]
        if not cells:
            continue
        texts = []
        for c in cells:
            if c.css_first("br, p, ul, ol, div, pre, table") is not None:
                return sanitize_node(node, base_url, as_tag="table")  # سلول چندخطی → HTML خام
            texts.append(inline(c, base_url).strip().replace("|", "\\|").replace("\n", " "))
        if header is None and all(c.tag == "th" for c in cells):
            header = texts
        else:
            rows.append(texts)
    if header is None and rows:
        header = rows.pop(0)
    if header is None:
        return ""
    width = max(len(header), *(len(r) for r in rows)) if rows else len(header)
    header = header + [""] * (width - len(header))
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for r in rows:
        r = r + [""] * (width - len(r))
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def block_to_markdown(node: Node, tag: str, base_url: str | None = None) -> str:
    """یک بلوک برنده (نود + نوع) → Markdown."""
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return f"{'#' * int(tag[1])} " + inline(node, base_url).strip().replace("\n", " ")
    if tag in ("ul", "ol"):
        return _list(node, base_url, 0)
    if tag == "table":
        return _table(node, base_url)
    if tag == "pre":
        code = node.text(deep=True).strip("\n")
        return f"```\n{code}\n```"
    if tag == "blockquote":
        body = inline(node, base_url).strip()
        return "\n".join("> " + ln if ln else ">" for ln in body.split("\n"))
    if tag == "figure":
        img = node if node.tag == "img" else node.css_first("img")
        parts: list[str] = []
        if img is not None:
            src = img_src(img.attributes, base_url)
            if src:
                parts.append(f"![{_esc((img.attributes.get('alt') or '').strip())}]({src})")
        cap = node.css_first("figcaption")
        if cap is not None:
            c = inline(cap, base_url).strip()
            if c:
                parts.append(c)
        return "\n\n".join(parts)
    return inline(node, base_url).strip()
