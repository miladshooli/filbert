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
        "low_confidence": rec.content.low_confidence,
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
) -> None:
    """استخراج محتوای اصلی و متادیتای SEO از URL یا فایل."""
    fmts = _parse_formats(formats)
    overrides: dict[str, object] = {"digits": digits}
    if cache_dir is not None:
        overrides["cache_dir"] = cache_dir
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
                on_result=on_result,
            )
        )

    table = Table(title=f"filbert run {stats.run_id}", show_lines=False)
    for col in ("status", "words", "blocks", "title", "source"):
        table.add_column(col)
    for rec, source, error in results:
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
    console.print(
        f"ok={stats.ok} failed={stats.failed} p50={stats.p50_ms}ms p95={stats.p95_ms}ms → {out / stats.run_id}"
    )
    if show_json:
        for rec, _source, _error in results:
            if rec is not None:
                sys.stdout.buffer.write(
                    orjson.dumps(summary_dict(rec), option=orjson.OPT_INDENT_2) + b"\n"
                )
    if stats.failed and not stats.ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
