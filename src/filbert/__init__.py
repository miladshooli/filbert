"""filbert — استخراج سریع و دقیق محتوای اصلی وب و متادیتای SEO، بهینه برای فارسی."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.6.0"
__all__ = ["__version__", "extract_html", "fetch_and_extract"]

if TYPE_CHECKING:
    from filbert.pipeline import extract_html, fetch_and_extract


def __getattr__(name: str) -> Any:
    # بارگذاری تنبل تا import سبک بماند و حلقه import پیش نیاید
    if name in ("extract_html", "fetch_and_extract"):
        from filbert import pipeline

        return getattr(pipeline, name)
    raise AttributeError(name)
