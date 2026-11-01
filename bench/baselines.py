"""خط پایه‌ها و استخراج‌گرهای filbert به‌صورت تابع یکنواخت `html, url -> text`.
Trafilatura فقط در همین فایل import می‌شود."""

from __future__ import annotations

from collections.abc import Callable

from filbert.config import Settings
from filbert.extract import cetd, domscore, ensemble, readability
from filbert.extract.domtext import parse
from filbert.extract.preclean import preclean
from filbert.extract.rules import load_rules
from filbert.pipeline import extract_html

Extractor = Callable[[str, str], str]
RULES = load_rules()


def _prepared(html: str):
    tree = parse(html)
    preclean(tree, RULES.preclean)
    return tree


def fb_readability(html: str, url: str) -> str:
    return readability.extract(_prepared(html), RULES.readability, url).text


def fb_cetd(html: str, url: str) -> str:
    return cetd.extract(_prepared(html), url).text


def fb_dom(html: str, url: str) -> str:
    return domscore.extract(_prepared(html), RULES.readability, url).text


def fb_ensemble(html: str, url: str) -> str:
    return ensemble.extract(_prepared(html), RULES, url).text


_SETTINGS = Settings(_env_file=None)


def fb_pipeline(html: str, url: str) -> str:
    """مسیر کامل محصول (همان چیزی که CLI می‌دهد؛ شامل نرمال‌سازی)."""
    return extract_html(html, url, settings=_SETTINGS).content.text or ""


def trafilatura_extract(html: str, url: str) -> str:
    import trafilatura  # noqa: PLC0415 — فقط در bench

    return (
        trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_precision=False,
            output_format="txt",
        )
        or ""
    )


FILBERT: dict[str, Extractor] = {
    "readability": fb_readability,
    "cetd": fb_cetd,
    "dom": fb_dom,
    "ensemble": fb_ensemble,
}
BASELINES: dict[str, Extractor] = {"trafilatura": trafilatura_extract}


def resolve(names: list[str]) -> dict[str, Extractor]:
    out: dict[str, Extractor] = {}
    for n in names:
        if n in FILBERT:
            out[n] = FILBERT[n]
        elif n in BASELINES:
            out[n] = BASELINES[n]
        else:
            raise KeyError(
                f"unknown extractor {n!r}; choose from {list(FILBERT) + list(BASELINES)}"
            )
    return out
