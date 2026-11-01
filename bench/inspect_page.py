"""کمک به انتخاب selector برای برچسب خودکار: `python -m bench.inspect_page <url>`
بزرگ‌ترین عناصر متنی را با tag/class/id، طول متن و چگالی لینک چاپ می‌کند؛ به‌علاوه خروجی readability."""

from __future__ import annotations

import asyncio
import sys

from filbert.config import Settings
from filbert.extract import readability
from filbert.extract.domtext import class_id, inner_text_len, link_density, parse, xpath_of
from filbert.extract.preclean import preclean
from filbert.extract.rules import load_rules
from filbert.fetch.cache import Cache
from filbert.fetch.client import Fetcher
from filbert.meta.head import extract_head


async def main(url: str) -> None:
    settings = Settings(_env_file=None)
    cache = Cache(settings.cache_dir)
    async with Fetcher(settings, cache) as f:
        r = await f.fetch(url)
    tree = parse(r.text)
    seo = extract_head(tree, r.final_url)
    print(
        f"status={r.status} final={r.final_url} len={len(r.text) // 1024}KB title={seo.title!r} lang={seo.lang_declared}"
    )
    rows = []
    for n in tree.body.traverse():
        if not n.is_element_node or n.tag in ("html", "body", "script", "style"):
            continue
        tl = inner_text_len(n)
        if tl < 300:
            continue
        rows.append((tl, round(link_density(n), 2), n.tag, class_id(n)[:60], xpath_of(n)))
    rows.sort(reverse=True)
    print("\n-- بزرگ‌ترین عناصر (len, link_density, tag, class/id, xpath):")
    for row in rows[:25]:
        print(row)
    rules = load_rules()
    preclean(tree, rules.preclean)
    res = readability.extract(tree, rules.readability, r.final_url)
    print(f"\n-- readability top={res.top_xpath} blocks={len(res.blocks)} chars={res.text_len}")
    print(res.text[:600].replace("\n", " | "))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
