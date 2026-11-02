"""قواعد ممیزی SEO روی `PageRecord` → فهرست مسئله‌ها (برای برگه issues در Excel و پنل)."""

from __future__ import annotations

from dataclasses import dataclass

from filbert.models import PageRecord

TITLE_MAX = 60
DESC_MIN, DESC_MAX, DESC_PX_MAX = 70, 160, 920
THIN_WORDS = 200


@dataclass(slots=True)
class Issue:
    code: str
    severity: str  # error | warning | info
    detail: str


def find_issues(rec: PageRecord) -> list[Issue]:
    seo, st, c = rec.seo, rec.structure, rec.content
    out: list[Issue] = []
    if not seo.title_tag:
        out.append(Issue("missing_title", "error", "تگ <title> ندارد"))
    elif (seo.title_length or 0) > TITLE_MAX:
        out.append(
            Issue("title_too_long", "warning", f"{seo.title_length} کاراکتر (> {TITLE_MAX})")
        )
    if not seo.description:
        out.append(Issue("missing_description", "error", "meta description ندارد"))
    else:
        if (seo.description_length or 0) < DESC_MIN:
            out.append(
                Issue(
                    "description_too_short",
                    "warning",
                    f"{seo.description_length} کاراکتر (< {DESC_MIN})",
                )
            )
        if (seo.description_length or 0) > DESC_MAX or (seo.description_px_est or 0) > DESC_PX_MAX:
            out.append(
                Issue(
                    "description_too_long",
                    "warning",
                    f"{seo.description_length} کاراکتر / ~{seo.description_px_est}px",
                )
            )
    h1s = [h for h in st.headings if h.level == 1]
    if not h1s:
        out.append(Issue("missing_h1", "error", "h1 ندارد"))
    elif len(h1s) > 1:
        out.append(Issue("multiple_h1", "warning", f"{len(h1s)} عدد h1"))
    if seo.title_tag and seo.h1 and seo.title_tag.strip() == seo.h1.strip():
        out.append(Issue("title_equals_h1", "info", "title و h1 یکسان‌اند"))
    if not seo.canonical:
        out.append(Issue("missing_canonical", "warning", "canonical ندارد"))
    elif rec.final_url and seo.canonical.rstrip("/") != rec.final_url.rstrip("/"):
        out.append(Issue("canonical_mismatch", "info", f"canonical={seo.canonical}"))
    if seo.robots.noindex:
        out.append(Issue("noindex", "warning", seo.robots.raw or ""))
    if st.images_summary.missing_alt:
        out.append(
            Issue(
                "images_missing_alt",
                "warning",
                f"{st.images_summary.missing_alt} از {st.images_summary.total} تصویر بدون alt",
            )
        )
    if (c.word_count or 0) < THIN_WORDS:
        out.append(Issue("thin_content", "warning", f"{c.word_count} کلمه"))
    if c.low_confidence:
        out.append(Issue("low_confidence", "info", "استخراج با اطمینان پایین (بازبینی دستی)"))
    if not seo.json_ld_types:
        out.append(Issue("no_structured_data", "info", "JSON-LD ندارد"))
    if not seo.lang_declared:
        out.append(Issue("missing_lang", "warning", "html[lang] ندارد"))
    elif seo.lang_detected in ("fa", "ar", "en") and seo.lang_declared != seo.lang_detected:
        out.append(
            Issue(
                "lang_mismatch",
                "warning",
                f"declared={seo.lang_declared} detected={seo.lang_detected}",
            )
        )
    return out
