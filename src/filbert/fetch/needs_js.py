"""تشخیص «نیاز به رندر JS» پیش از Playwright، بدون LLM (بخش ۳ لایه دریافت).

صفحه رندر می‌شود اگر دست‌کم یکی برقرار باشد:
- متن قابل‌مشاهده body < 400 کاراکتر در حالی که HTML > 50KB،
- `div#root` / `#app` / `#__next` / `#__nuxt` خالی یا فقط `<noscript>`،
- نسبت بایت `<script>` به کل > 0.6،
- دامنه در فهرست «همیشه رندر».
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from filbert.extract.domtext import Tree, inner_text_len
from filbert.fetch.urlnorm import registered_domain

MIN_VISIBLE_CHARS = 400
MIN_HTML_BYTES = 50 * 1024
MAX_SCRIPT_RATIO = 0.6
_SHELL_IDS = ("root", "app", "__next", "__nuxt", "__layout", "application")
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)


@dataclass(slots=True)
class JsVerdict:
    needs_js: bool
    reasons: list[str] = field(default_factory=list)
    visible_chars: int = 0
    html_bytes: int = 0
    script_ratio: float = 0.0


def _visible_chars(tree: Tree) -> int:
    body = tree.body
    if body is None:
        return 0
    total = inner_text_len(body)
    for tag in ("script", "style", "noscript", "template"):
        for n in body.css(tag):
            total -= inner_text_len(n)
    return max(0, total)


def _shell_empty(tree: Tree) -> str | None:
    for sid in _SHELL_IDS:
        n = tree.css_first(f"#{sid}")
        if n is None:
            continue
        txt = inner_text_len(n)
        for ns in n.css("noscript"):
            txt -= inner_text_len(ns)
        if txt < 50:
            return sid
    return None


def needs_js(
    html: str, tree: Tree, url: str | None = None, always_render: frozenset[str] = frozenset()
) -> JsVerdict:
    html_bytes = len(html.encode("utf-8", "ignore"))
    script_bytes = sum(len(m.group(0).encode("utf-8", "ignore")) for m in _SCRIPT_RE.finditer(html))
    ratio = script_bytes / html_bytes if html_bytes else 0.0
    visible = _visible_chars(tree)
    v = JsVerdict(False, visible_chars=visible, html_bytes=html_bytes, script_ratio=round(ratio, 3))
    if url and always_render:
        dom = registered_domain(urlsplit(url).hostname or "")
        if dom in always_render:
            v.reasons.append("always_render_domain")
    if visible < MIN_VISIBLE_CHARS and html_bytes > MIN_HTML_BYTES:
        v.reasons.append("thin_text_large_html")
    shell = _shell_empty(tree)
    if shell is not None and visible < MIN_VISIBLE_CHARS:
        v.reasons.append(f"empty_shell:#{shell}")
    if ratio > MAX_SCRIPT_RATIO:
        v.reasons.append("script_heavy")
    v.needs_js = bool(v.reasons)
    return v
