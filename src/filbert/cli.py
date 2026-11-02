"""CLI با typer: `filbert extract <url|file>... --out out/ --formats json,html,md`."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Annotated

import orjson
import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from filbert import __version__
from filbert.config import Settings
from filbert.models import PageRecord
from filbert.out.store import FORMATS

app = typer.Typer(
    help="filbert — استخراج سریع و دقیق محتوای وب، بهینه برای فارسی.", no_args_is_help=True
)
console = Console(stderr=True)


def _setup_logging(verbose: int) -> None:
    level = logging.WARNING if verbose == 0 else logging.INFO if verbose == 1 else logging.DEBUG
    logging.basicConfig(
        level=level, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr
    )


def _parse_formats(formats: str) -> tuple[str, ...]:
    parts = tuple(p.strip().lower() for p in formats.split(",") if p.strip())
    bad = [p for p in parts if p not in FORMATS]
    if bad or not parts:
        raise typer.BadParameter(
            f"formats must be a subset of {','.join(FORMATS)}; got {formats!r}"
        )
    return parts


def summary_dict(rec: PageRecord) -> dict[str, object]:
    return {
        "url": rec.final_url or rec.url,
        "status": rec.http.status,
        "from_cache": rec.http.from_cache,
        "title": rec.seo.title,
        "title_source": rec.seo.title_source,
        "description": (rec.seo.description or "")[:120] or None,
        "canonical": rec.canonical,
        "lang": rec.seo.lang_declared,
        "robots": rec.seo.robots.raw,
        "blocks": len(rec.content.blocks),
        "word_count": rec.content.word_count,
        "char_count": rec.content.char_count,
        "confidence": rec.content.confidence,
        "low_confidence": rec.content.low_confidence,
        "extractors": rec.content.extractors,
        "content_hash": rec.content_hash,
        "text_preview": (rec.content.text or "")[:160],
    }


@app.callback()
def main(
    verbose: Annotated[
        int, typer.Option("--verbose", "-v", count=True, help="-v info, -vv debug")
    ] = 0,
) -> None:
    _setup_logging(verbose)


@app.command()
def version() -> None:
    """نسخه ابزار."""
    typer.echo(f"filbert {__version__}")


@app.command()
def extract(
    inputs: Annotated[list[str], typer.Argument(help="URL یا مسیر فایل HTML (چندتایی)")],
    out: Annotated[
        Path, typer.Option("--out", "-o", help="پوشه خروجی (یک زیرپوشه run-id ساخته می‌شود)")
    ] = Path("out"),
    formats: Annotated[str, typer.Option("--formats", "-f", help="json,html,md")] = "json,html,md",
    cache_dir: Annotated[
        Path | None, typer.Option("--cache-dir", help="پوشه کش (پیش‌فرض از config)")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="کش را نادیده بگیر و دوباره دانلود کن")
    ] = False,
    show_json: Annotated[
        bool, typer.Option("--json", help="خلاصه JSON هر صفحه را در stdout چاپ کن")
    ] = False,
    digits: Annotated[str, typer.Option("--digits", help="fa یا en")] = "fa",
    recall: Annotated[
        bool, typer.Option("--recall", help="اتحاد سه استخراج‌گر (بیشینه recall)")
    ] = False,
    render: Annotated[
        str, typer.Option("--render", help="never | auto | always (نیاز به extras render)")
    ] = "never",
    workers: Annotated[
        int | None,
        typer.Option("--workers", help="پردازه‌های استخراج (پیش‌فرض: تعداد هسته؛ 1 = inline)"),
    ] = None,
    ignore_robots: Annotated[
        bool,
        typer.Option("--ignore-robots", help="robots.txt را نادیده بگیر (فقط دامنه‌های خودتان)"),
    ] = False,
    only_changed: Annotated[
        bool,
        typer.Option("--only-changed", help="فقط صفحاتی که content_hash تغییر کرده نوشته شوند"),
    ] = False,
) -> None:
    """استخراج محتوای اصلی و متادیتای SEO از URL یا فایل."""
    _run(
        inputs,
        out,
        formats,
        cache_dir,
        force,
        show_json,
        digits,
        recall,
        render,
        workers,
        ignore_robots,
        only_changed,
    )


@app.command()
def crawl(
    sitemap: Annotated[
        str | None, typer.Option("--sitemap", help="URL سایت‌مپ (index هم پشتیبانی می‌شود)")
    ] = None,
    urls_file: Annotated[
        Path | None, typer.Option("--urls", help="فایل متنی، هر خط یک URL")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="سقف تعداد URL")] = 10_000,
    pattern: Annotated[str | None, typer.Option("--pattern", help="regex شامل‌کردن URLها")] = None,
    exclude: Annotated[str | None, typer.Option("--exclude", help="regex حذف URLها")] = None,
    concurrency: Annotated[int, typer.Option("--concurrency", help="کارگران دریافت همزمان")] = 32,
    out: Annotated[Path, typer.Option("--out", "-o")] = Path("out"),
    formats: Annotated[str, typer.Option("--formats", "-f")] = "json,html,md",
    cache_dir: Annotated[Path | None, typer.Option("--cache-dir")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
    digits: Annotated[str, typer.Option("--digits")] = "fa",
    recall: Annotated[bool, typer.Option("--recall")] = False,
    render: Annotated[str, typer.Option("--render")] = "never",
    workers: Annotated[int | None, typer.Option("--workers")] = None,
    ignore_robots: Annotated[bool, typer.Option("--ignore-robots")] = False,
    only_changed: Annotated[bool, typer.Option("--only-changed")] = False,
    webhook: Annotated[str | None, typer.Option("--webhook")] = None,
) -> None:
    """خزش از سایت‌مپ یا فایل URL؛ استخراج موازی؛ فقط صفحات تغییرکرده با --only-changed."""
    if not sitemap and not urls_file:
        raise typer.BadParameter("--sitemap یا --urls لازم است")
    overrides: dict[str, object] = {"concurrency": concurrency}
    if cache_dir is not None:
        overrides["cache_dir"] = cache_dir
    settings = Settings(**overrides)
    inputs: list[str] = []
    if urls_file is not None:
        from filbert.fetch.sitemap import read_url_file

        inputs += read_url_file(urls_file.read_text(encoding="utf-8").splitlines())
    if sitemap:
        from filbert.fetch.cache import Cache
        from filbert.fetch.client import Fetcher
        from filbert.fetch.sitemap import urls_from_sitemap

        async def discover() -> list[str]:
            cache = Cache(settings.cache_dir)
            try:
                async with Fetcher(settings, cache) as f:
                    return await urls_from_sitemap(
                        f, sitemap, limit=limit, pattern=pattern, exclude=exclude
                    )
            finally:
                cache.close()

        with console.status("reading sitemap…"):
            inputs += asyncio.run(discover())
    inputs = list(dict.fromkeys(inputs))[:limit]
    console.print(f"{len(inputs)} URL")
    if not inputs:
        raise typer.Exit(code=1)
    _run(
        inputs,
        out,
        formats,
        cache_dir,
        force,
        False,
        digits,
        recall,
        render,
        workers,
        ignore_robots,
        only_changed,
        concurrency=concurrency,
    )


def _run(
    inputs: list[str],
    out: Path,
    formats: str,
    cache_dir: Path | None,
    force: bool,
    show_json: bool,
    digits: str,
    recall: bool,
    render: str,
    workers: int | None,
    ignore_robots: bool,
    only_changed: bool,
    concurrency: int | None = None,
    webhook: str | None = None,
    dom_model: Path | None = None,
) -> None:
    fmts = _parse_formats(formats)
    if render not in ("never", "auto", "always"):
        raise typer.BadParameter("--render must be never|auto|always")
    overrides: dict[str, object] = {
        "digits": digits,
        "recall": recall,
        "render": render,
        "workers": workers,
        "respect_robots": not ignore_robots,
    }
    if cache_dir is not None:
        overrides["cache_dir"] = cache_dir
    if concurrency is not None:
        overrides["concurrency"] = concurrency
    if webhook:
        overrides["webhook_url"] = webhook
    if dom_model is not None:
        overrides["dom_model_path"] = dom_model
    settings = Settings(**overrides)

    from filbert.pipeline import fetch_and_extract

    results: list[tuple[PageRecord | None, str, str | None]] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("extracting", total=len(inputs))

        def on_result(rec: PageRecord | None, source: str, error: str | None) -> None:
            results.append((rec, source, error))
            progress.advance(task)

        stats, _records = asyncio.run(
            fetch_and_extract(
                inputs,
                settings=settings,
                out_dir=out,
                formats=fmts,
                force=force,
                only_changed=only_changed,
                on_result=on_result,
            )
        )

    table = Table(title=f"filbert run {stats.run_id}", show_lines=False)
    for col in ("status", "words", "blocks", "title", "source"):
        table.add_column(col)
    shown = results if len(results) <= 40 else results[:40]
    for rec, source, error in shown:
        if rec is None:
            table.add_row("[red]ERR", "-", "-", f"[red]{error}", source)
        else:
            st = str(rec.http.status or "file") + (" (cache)" if rec.http.from_cache else "")
            flag = " [yellow]low" if rec.content.low_confidence else ""
            table.add_row(
                st,
                str(rec.content.word_count),
                str(len(rec.content.blocks)),
                (rec.seo.title or "")[:60] + flag,
                source,
            )
    console.print(table)
    if len(results) > 40:
        console.print(f"… و {len(results) - 40} مورد دیگر")
    console.print(
        f"ok={stats.ok} failed={stats.failed} rendered={stats.rendered} unchanged={stats.skipped_unchanged} "
        f"robots={stats.robots_blocked} p50={stats.p50_ms}ms p95={stats.p95_ms}ms → {out / stats.run_id}"
    )
    if show_json:
        for rec, _source, _error in results:
            if rec is not None:
                sys.stdout.buffer.write(
                    orjson.dumps(summary_dict(rec), option=orjson.OPT_INDENT_2) + b"\n"
                )
    if stats.failed and not stats.ok:
        raise typer.Exit(code=1)


@app.command()
def export(
    source: Annotated[Path, typer.Argument(help="پوشه run یا فایل pages.jsonl")],
    xlsx: Annotated[Path, typer.Option("--xlsx", help="مسیر فایل Excel خروجی")],
    no_chunks: Annotated[bool, typer.Option("--no-chunks", help="برگه chunks ساخته نشود")] = False,
) -> None:
    """خروجی Excel (pages / issues / headings / links / images / chunks) از یک run."""
    from filbert.out.excel import export_xlsx

    counts = export_xlsx(source, xlsx, include_chunks=not no_chunks)
    console.print(" ".join(f"{k}={v}" for k, v in counts.items()) + f" → {xlsx}")


@app.command()
def chunk(
    inputs: Annotated[list[str], typer.Argument(help="URL یا فایل HTML")],
    max_words: Annotated[int, typer.Option("--max", help="بودجه هدف (کلمه)")] = 250,
    hard_max: Annotated[int, typer.Option("--hard-max")] = 400,
    overlap: Annotated[int, typer.Option("--overlap", help="هم‌پوشانی جمله‌ای")] = 1,
    level: Annotated[int, typer.Option("--level", help="مرز سخت هدینگ تا سطح مؤثر N")] = 3,
    unit: Annotated[str, typer.Option("--unit", help="words | chars | tiktoken")] = "words",
    no_context: Annotated[
        bool, typer.Option("--no-context", help="بدون پیشوند زمینه‌ای در embed_text")
    ] = False,
    out: Annotated[
        Path | None, typer.Option("--out", help="فایل JSONL خروجی (پیش‌فرض: stdout خلاصه)")
    ] = None,
    cache_dir: Annotated[Path | None, typer.Option("--cache-dir")] = None,
) -> None:
    """چانک‌های embedding-آماده از صفحه (docs/CHUNKING.md)."""
    overrides: dict[str, object] = {
        "chunk_max_words": max_words,
        "chunk_hard_max": hard_max,
        "chunk_overlap_sentences": overlap,
        "chunk_heading_level": level,
        "chunk_unit": unit,
        "chunk_context_prefix": not no_context,
        "respect_robots": False,
        "workers": 1,
    }
    if cache_dir is not None:
        overrides["cache_dir"] = cache_dir
    settings = Settings(**overrides)
    from filbert.pipeline import fetch_and_extract

    _stats, records = asyncio.run(fetch_and_extract(inputs, settings=settings))
    lines = []
    for rec in records:
        for ch in rec.content.chunks:
            lines.append(
                orjson.dumps({"url": rec.final_url or rec.url, **ch.model_dump(mode="json")})
            )
    if out is not None:
        out.write_bytes(b"\n".join(lines) + (b"\n" if lines else b""))
        console.print(f"{len(lines)} chunks → {out}")
        return
    for rec in records:
        console.print(f"[bold]{rec.final_url or rec.url}[/] — {len(rec.content.chunks)} chunks")
        for ch in rec.content.chunks:
            path = " › ".join(ch.heading_path) or "-"
            console.print(
                f"  #{ch.index:03d} {ch.word_count:4d}w [{','.join(ch.block_types)}] {path}"
            )
            console.print(
                f"       {ch.text[:110].replace(chr(10), ' ')}…"
                if len(ch.text) > 110
                else f"       {ch.text.replace(chr(10), ' ')}"
            )


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def bench(
    ctx: typer.Context,
    dataset: Annotated[
        list[str] | None, typer.Option("--dataset", "-d", help="نام دیتاست (چندتایی)")
    ] = None,
    compare_with: Annotated[
        str, typer.Option("--compare-with", help="خط پایه‌ها، مثلاً trafilatura")
    ] = "",
    check: Annotated[
        bool, typer.Option("--check", help="خطا در افت نسبت به baseline.json")
    ] = False,
) -> None:
    """اجرای bench روی دیتاست‌ها (نیاز به ریشه مخزن و extras `bench`)."""
    import sys as _sys
    from pathlib import Path as _Path

    try:
        from bench import run as bench_run
    except ImportError:
        if (_Path.cwd() / "bench" / "run.py").exists():
            _sys.path.insert(0, str(_Path.cwd()))
            from bench import run as bench_run
        else:
            console.print("[red]bench package not found; run from the repository root.")
            raise typer.Exit(code=2) from None
    argv: list[str] = []
    for d in dataset or []:
        argv += ["--dataset", d]
    if compare_with:
        argv += ["--compare-with", compare_with]
    if check:
        argv.append("--check")
    argv += list(ctx.args)
    raise typer.Exit(code=bench_run.main(argv))


if __name__ == "__main__":
    app()
