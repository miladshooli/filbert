"""دیتاست `fixtures` را از ۵ fixture تست می‌سازد؛ gold با selectorهای شناخته‌شده همان fixtureها
(مستقل از استخراج‌گرها). `python -m bench.make_fixtures_dataset`"""

from __future__ import annotations

from pathlib import Path

from bench.datasets import Dataset, Page
from bench.selectors import gold_from_selectors

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
SPEC: dict[str, dict] = {
    "news": {
        "url": "https://news.example.ir/economy/123456/",
        "type": "news",
        "include": ["article h1", "article .lead", "article .news-body"],
        "exclude": [],
        "meta": {
            "title": "افزایش قیمت بیت‌کوین در بازار امروز - خبرگزاری نمونه",
            "description": "بیت‌کوین امروز با رشد ۴ درصدی به بالاترین سطح دو ماه اخیر رسید.",
            "canonical": "https://news.example.ir/economy/123456/",
            "author": "سارا احمدی",
            "published_at": "2026-10-31T09:00:00+03:30",
        },
    },
    "blog": {
        "url": "https://blog.example.ir/hardware-wallet/",
        "type": "blog",
        "include": ["article h1.entry-title", "article .entry-content"],
        "exclude": [],
        "meta": {
            "title": "چطور کیف پول سخت‌افزاری بخریم؟ | بلاگ نمونه",
            "description": "راهنمای خرید کیف پول سخت‌افزاری برای تازه‌کارها",
            "author": "علی",
        },
    },
    "product": {
        "url": "https://shop.example.ir/product/x12/",
        "type": "product",
        "include": ["h1.product-title", "#description"],
        "exclude": [],
        "meta": {"title": "خرید گوشی نمونه ۱۲۸ گیگابایت | فروشگاه"},
    },
    "landing": {
        "url": "https://exchange.example.ir/",
        "type": "landing",
        "include": [
            "section.hero h1",
            "section.hero p",
            "section.features",
            "section.steps",
            "section.faq",
        ],
        "exclude": [],
        "meta": {
            "title": "خرید و فروش ارز دیجیتال | صرافی نمونه",
            "description": "امن‌ترین صرافی ارز دیجیتال ایران",
        },
    },
    "forum": {
        "url": "https://forum.example.ir/t/usdt-tron/",
        "type": "forum",
        "include": ["h1.topic-title", ".cooked"],
        "exclude": [],
        "meta": {"title": "مشکل برداشت تتر از شبکه ترون - انجمن نمونه"},
    },
}


def main() -> None:
    ds = Dataset("fixtures")
    ds.create()
    pages: list[Page] = []
    for name, spec in SPEC.items():
        html = (FIXTURES / f"{name}.html").read_text(encoding="utf-8")
        page = Page(
            id=name, url=spec["url"], type=spec["type"], label_status="gold", site="fixture"
        )
        pages.append(page)
        ds.put_html(name, html)
        text = gold_from_selectors(html, spec["include"], spec["exclude"])
        ds.put_gold(name, text, spec["meta"])
    ds.write_index(pages)
    print(f"fixtures dataset: {len(pages)} pages → {ds.root}")


if __name__ == "__main__":
    main()
