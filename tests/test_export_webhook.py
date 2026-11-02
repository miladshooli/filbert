import json
from pathlib import Path

import httpx
import pytest
from pytest_httpserver import HTTPServer
from typer.testing import CliRunner
from werkzeug.wrappers import Request, Response

from filbert.cli import app
from filbert.config import Settings
from filbert.out.excel import export_xlsx
from filbert.out.issues import find_issues
from filbert.out.store import Store
from filbert.out.webhook import WebhookSender
from filbert.pipeline import extract_html, fetch_and_extract
from tests.conftest import fixture_html

runner = CliRunner()


def _run_dir(tmp_path: Path) -> Path:
    st = Store(tmp_path, run_id="r", formats=("json",))
    for name, url in (
        ("news", "https://news.example.ir/economy/123456/"),
        ("product", "https://shop.example.ir/p/1"),
    ):
        st.write(extract_html(fixture_html(f"{name}.html"), url))
    st.close()
    return tmp_path / "r"


def test_issues_rules() -> None:
    news = extract_html(fixture_html("news.html"), "https://news.example.ir/economy/123456/")
    codes = {i.code for i in find_issues(news)}
    assert "missing_title" not in codes and "missing_h1" not in codes
    assert "description_too_short" in codes  # توضیح کوتاه fixture
    product = extract_html(fixture_html("product.html"), "https://shop.example.ir/p/1")
    pcodes = {i.code for i in find_issues(product)}
    assert {"missing_description", "missing_canonical", "images_missing_alt"} <= pcodes
    assert "lang_mismatch" not in pcodes


def test_export_xlsx(tmp_path: Path) -> None:
    load_workbook = pytest.importorskip("openpyxl").load_workbook

    run_dir = _run_dir(tmp_path)
    out = tmp_path / "seo.xlsx"
    counts = export_xlsx(run_dir, out)
    assert counts["pages"] == 2 and counts["issues"] > 0 and counts["chunks"] > 0
    wb = load_workbook(out)
    assert wb.sheetnames == ["pages", "issues", "headings", "links", "images", "chunks"]
    ws = wb["pages"]
    assert ws.sheet_view.rightToLeft and ws.freeze_panes == "A2"
    header = [c.value for c in ws[1]]
    row = dict(zip(header, [c.value for c in ws[2]], strict=False))
    assert row["title"].startswith("افزایش قیمت بیت‌کوین")  # ZWNJ حفظ شد
    assert row["word_count"] > 100 and row["author"] == "سارا احمدی"
    issues = [[c.value for c in r] for r in wb["issues"].iter_rows(min_row=2)]
    assert any(r[2] == "missing_description" for r in issues)


def test_cli_export(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    run_dir = _run_dir(tmp_path)
    result = runner.invoke(
        app, ["export", str(run_dir), "--xlsx", str(tmp_path / "x.xlsx"), "--no-chunks"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "x.xlsx").exists() and "pages=2" in result.output


async def test_webhook_batches_signature_and_retry(httpserver: HTTPServer) -> None:
    got: list[tuple[dict, bytes]] = []
    calls = {"n": 0}

    def handler(req: Request) -> Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return Response("busy", status=503)
        got.append((dict(req.headers), req.get_data()))
        return Response("ok", status=200)

    httpserver.expect_request("/hook", method="POST").respond_with_handler(handler)
    rec = extract_html(fixture_html("news.html"), "https://news.example.ir/x/")
    async with httpx.AsyncClient() as client:
        sender = WebhookSender(
            httpserver.url_for("/hook"),
            secret="s3cret",
            batch_size=2,
            retries=2,
            run_id="r1",
            client=client,
        )
        sender.retries = 2
        async with sender:
            for _ in range(3):
                await sender.add(rec)
    assert sender.stats == {"sent": 3, "batches": 2, "failed_batches": 0} and calls["n"] == 3
    import hashlib
    import hmac

    headers, body = got[0]
    payload = json.loads(body)
    assert (
        payload["run_id"] == "r1"
        and payload["count"] == 2
        and payload["records"][0]["seo"]["title"]
    )
    assert (
        headers["X-Filbert-Signature"]
        == "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    )


async def test_pipeline_webhook(httpserver: HTTPServer, settings: Settings, tmp_path: Path) -> None:
    received = []
    httpserver.expect_request("/news").respond_with_data(
        fixture_html("news.html"), content_type="text/html"
    )
    httpserver.expect_request("/hook", method="POST").respond_with_handler(
        lambda r: (received.append(r.get_data()), Response("ok"))[1]
    )
    s = settings.model_copy(
        update={
            "respect_robots": False,
            "workers": 1,
            "webhook_url": httpserver.url_for("/hook"),
            "webhook_batch": 1,
        }
    )
    stats, _ = await fetch_and_extract(
        [httpserver.url_for("/news")], settings=s, out_dir=tmp_path / "out"
    )
    assert (
        stats.settings["webhook"] == {"sent": 1, "batches": 1, "failed_batches": 0}
        and len(received) == 1
    )
