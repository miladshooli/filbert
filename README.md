# filbert

[![ci](https://github.com/miladshooli/filbert/actions/workflows/ci.yml/badge.svg)](https://github.com/miladshooli/filbert/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Fast, accurate main-content and SEO-metadata extraction for the web, tuned for Persian (Farsi) and RTL pages.**

🇮🇷 [راهنمای فارسی](README.fa.md)

filbert takes a URL (or raw HTML) and returns the article body as clean text, semantic HTML and Markdown, plus everything an SEO audit needs: title chain, description, canonical, robots, Open Graph, JSON-LD, author, publish date (Jalali dates included), headings, links, images, language, and embedding-ready chunks. No LLM in the main path: three deterministic extractors vote on every block, and the whole pipeline runs in about 15 ms per page.

## Why another extractor?

Existing tools (Trafilatura, Readability, newspaper) are tuned on English news. Persian sites bring their own problems: ZWNJ inside words, Arabic-vs-Persian letter forms, Jalali dates, Finglish boilerplate class names (`nazarat`, `tabligh`, `matalebe-mortabet`), and a lot of React/Nuxt storefronts. filbert was built against a 200-page, hand-labelled Persian benchmark covering news, blogs, product pages, landing pages and forums.

Two human-labelled Persian benchmarks, token-level F1 of the main content:

| Dataset | pages | **filbert** | Trafilatura 2.3 | pages with F1 > 0.9 (filbert / Trafilatura) |
| --- | --- | --- | --- | --- |
| `fa-200`: news, blogs, product, landing, forum pages from 21 sites | 202 | **0.861** | 0.728 | 58% / 33% |
| `fa-biz-100`: blog posts of 45 Iranian businesses in 13 sectors | 84 | **0.956** | 0.839 | 90% / 44% |

| `fa-200` by page type | news | blog | product | landing | forum |
| --- | --- | --- | --- | --- | --- |
| filbert | 0.938 | 0.957 | 0.804 | 0.827 | 0.698 |
| Trafilatura | 0.842 | 0.909 | 0.706 | 0.503 | 0.511 |

On `fa-biz-100` filbert leads in every sector, from edu/HR/media (≥ 0.99) to fintech and cloud (0.91 / 0.89). Metadata fields (title, description, canonical, published date, author) match the gold labels on 100% of pages where the site declares them. Full report: [bench/report.md](bench/report.md).

## Install

```bash
pip install "git+https://github.com/miladshooli/filbert"
# with optional features:
pip install "filbert[render,export,llm] @ git+https://github.com/miladshooli/filbert"
playwright install chromium   # only for --render
```

Extras: `server` (HTTP API), `render` (Playwright for JS-heavy pages), `export` (Excel), `llm` (schema-based extraction with the Anthropic SDK), `ml`, `lang`, `bench` (Trafilatura baseline, benchmark only).

Requires Python 3.12+. Works on macOS, Linux and Windows.

## Quick start

```bash
filbert extract https://nobitex.ir/mag/ --out out/ --formats json,html,md --json
filbert crawl --sitemap https://example.ir/sitemap.xml --limit 500 --only-changed --out out/
filbert chunk https://example.ir/post --max 250 --overlap 1 --out chunks.jsonl
filbert export out/<run-id> --xlsx seo.xlsx
filbert llm https://example.ir/post --schema seo          # needs ANTHROPIC_API_KEY
```

```python
from filbert import extract_html

rec = extract_html(html, url="https://example.ir/post")
rec.seo.title, rec.seo.published_at, rec.seo.author      # metadata with *_source fields
rec.content.text, rec.content.markdown                   # normalized Persian text / Markdown
rec.content.confidence, rec.content.blocks               # per-block votes from the ensemble
rec.content.chunks[0].embed_text                         # "title › heading path\n\nchunk"
rec.structure.links_summary, rec.structure.images_summary
rec.model_dump_json()                                    # the same JSON the CLI writes
```

Async fetching with caching, conditional rendering and a process pool:

```python
import asyncio
from filbert import fetch_and_extract
from filbert.config import Settings

stats, records = asyncio.run(fetch_and_extract(
    ["https://nobitex.ir/mag/", "https://www.zoomit.ir/"],
    settings=Settings(render="auto", workers=4),
    out_dir="out", formats=("json", "md"),
))
```

Every run writes `out/<run-id>/` with `pages.jsonl` (one `PageRecord` per line), `chunks.jsonl`, `errors.jsonl`, `run.json` and per-page `json/`, `html/`, `md/` files.

## Run it as an HTTP API

Put filbert on a server and call it from any language:

```bash
cp .env.example .env            # set FILBERT_API_KEYS
docker compose up -d --build    # → http://localhost:8000/docs
# or without Docker:
pip install "filbert[server,export] @ git+https://github.com/miladshooli/filbert"
FILBERT_API_KEYS=change-me filbert serve --host 0.0.0.0 --workers 4
```

```bash
curl -s localhost:8000/v1/extract -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.ir/post", "fields": ["seo", "content.text", "content.chunks"]}'
```

`POST /v1/extract` (one URL or raw HTML), `POST /v1/extract/batch` (up to 20 URLs), `POST /v1/jobs` (background crawl of a URL list or sitemap, results as NDJSON pages, chunks and an Excel SEO report), and an optional `POST /v1/llm`. API keys, an SSRF guard that refuses private and cloud-metadata addresses (on every redirect too), size limits and an OpenAPI page at `/docs` are built in. Release tags also publish `ghcr.io/miladshooli/filbert`. Full guide: [docs/API.md](docs/API.md) (Persian).

## What you get per page

```jsonc
{
  "url": "...", "final_url": "...", "canonical": "...", "fetched_at": "...",
  "http": { "status": 200, "response_ms": 412, "rendered": false, "from_cache": false, "detected_encoding": "utf-8" },
  "seo": {
    "title": "...", "title_source": "title_tag", "title_tag": "...", "og_title": "...", "h1": "...",
    "description": "...", "description_length": 136, "description_px_est": 876,
    "canonical": "...", "robots": { "raw": "index, follow", "noindex": false, "nofollow": false },
    "lang_declared": "fa", "lang_detected": "fa", "lang_scores": { "arabic_script": 0.99, "fa_vs_ar": 1.0 },
    "author": "...", "author_source": "json_ld",
    "published_at": "2026-11-01T12:26:30+00:00", "published_at_raw": "۱۰ آبان ۱۴۰۵", "published_at_source": "date_class",
    "open_graph": { "og:image": "https://..." }, "twitter": {}, "json_ld": [ ... ], "json_ld_types": ["NewsArticle"]
  },
  "content": {
    "text": "...", "text_raw": "...", "html": "<article lang=\"fa\" dir=\"rtl\">...</article>", "markdown": "# ...",
    "blocks": [{ "type": "p", "text": "...", "xpath": "/html/body/...", "votes": 3 }],
    "chunks": [{ "index": 0, "heading_path": ["..."], "text": "...", "embed_text": "...", "word_count": 180 }],
    "word_count": 1240, "reading_time_min": 6, "confidence": 0.94, "low_confidence": false,
    "extractors": { "readability": 1.0, "cetd": 0.97, "dom": 0.93 }
  },
  "structure": { "headings": [...], "links": [...], "images": [...], "links_summary": {...}, "images_summary": {...} },
  "content_hash": "a3f9...", "raw_html_ref": "cache/raw/<sha256>.html.zst"
}
```

## How it works

```
fetch (httpx, HTTP/2, per-host limits, ETag/304, zstd cache)
  └─ needs-JS heuristic ──► Playwright render (optional)
parse once (selectolax / lexbor)
  ├─ metadata from the full tree: head, JSON-LD, OG/Twitter, author, dates, structure
  └─ preclean ──► Readability rewrite ─┐
                  CETD (text density) ─┼─► block-level voting ──► clean HTML / Markdown / chunks
                  DOM feature scorer ──┘
```

- **Fetch layer:** async with connection pooling, per-host concurrency and spacing, exponential retry on 429/5xx/timeouts, conditional requests, raw HTML stored compressed so you can re-extract without the network, robots.txt, sitemap crawling, `--only-changed` via content hashes.
- **Extraction:** a Mozilla-Readability rewrite, Composite Text Density (SIGIR 2011) and a DOM feature scorer run on one parse tree and vote per block; blocks with two or more votes are kept, with gap filling and a recall fallback. Container and leaf granularity are reconciled so a `ul` from one extractor and its `li` children from another agree.
- **Persian handling:** ZWNJ is never dropped; Arabic letters and digits are normalized only in content, never in metadata; Finglish boilerplate patterns live in an editable YAML; word counts treat ZWNJ as a non-boundary; Jalali dates are parsed to ISO; language detection separates Persian from Arabic.
- **Chunking:** structure-aware chunks built from blocks (heading hierarchy, sentence-boundary splits, tables/code/lists never cut mid-way, sentence overlap, tiny sections merged), with an `embed_text` that carries the title and heading path. Design notes in [docs/CHUNKING.md](docs/CHUNKING.md).
- **Outputs for an SEO panel:** 15 audit rules (title/description length and pixel width, h1 problems, canonical mismatch, noindex, missing alt, thin content, language mismatch…), Excel export with pages/issues/headings/links/images/chunks sheets, and a signed webhook (`X-Filbert-Signature`, HMAC-SHA256).
- **Optional LLM layer:** `filbert llm` fills a Pydantic schema (built-in `article` and `seo`, or your own JSON Schema) from the clean Markdown with the official Anthropic SDK, with prompt caching and a disk cache. It never sits in the main path.

## Performance

Measured on the 202-page benchmark, cached HTML, Apple M-series laptop (4 performance + 4 efficiency cores):

| | value |
| --- | --- |
| pipeline p50 / p95 per page | 16 ms / 51 ms |
| extraction ensemble only, p50 | 9 ms |
| throughput, 1 / 4 / 8 processes | 41 / 105 / 115 pages per second |
| 10,000 documents, 8 workers | 177 pages per second, 0 errors |
| peak memory on the largest page (1.9 MB HTML) | 15 MB |

## Configuration

All settings live in `filbert.config.Settings` (pydantic-settings) and can be set from `.env` or `FILBERT_*` environment variables: `FILBERT_CACHE_DIR`, `FILBERT_CONCURRENCY`, `FILBERT_RENDER=auto`, `FILBERT_WORKERS`, `FILBERT_WEBHOOK_URL`, `FILBERT_WEBHOOK_SECRET`, `FILBERT_CHUNK_MAX_WORDS`, `FILBERT_DIGITS=en`, `FILBERT_BOILERPLATE_PATH` (your own boilerplate YAML), and more. See [docs/USAGE.md](docs/USAGE.md).

## Benchmark and development

```bash
git clone https://github.com/miladshooli/filbert && cd filbert
uv sync --all-extras --group dev
uv run --all-extras pytest -q                 # 268 tests
make bench                                    # all datasets vs Trafilatura, regression gate
uv run --all-extras python -m bench.speed     # p50/p95 and throughput
```

The `fa-200` dataset (news, blogs, product, landing and forum pages from 21 Persian sites) and `fa-biz-100` (blog posts from 45 Iranian businesses across fintech, insurance, travel, retail, education, health, cloud and more), both with human-reviewed gold labels, ship in `bench/datasets/`. `bench/collect.py` rebuilds it from `bench/sources.yml`; `bench/label.py` and the online review tool produce gold labels; `bench/promote_labels.py` applies them.

Design document: [docs/BLUEPRINT.md](docs/BLUEPRINT.md). Decisions log: [docs/DECISIONS.md](docs/DECISIONS.md). Changelog: [CHANGELOG.md](CHANGELOG.md).

## Status and roadmap

Phases 1 to 5 of the blueprint are implemented (core, ensemble, metadata, scale, chunking/exports/LLM). Open items: a 2-hour Playwright stability run on Windows, the 300 pages/s target (currently 177 on a laptop), and an optional embedding-based semantic chunking mode. Issues and pull requests are welcome, especially new boilerplate patterns for Persian CMS themes and more labelled pages.

## License

MIT © Milad Shooli
