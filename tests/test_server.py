import time
from pathlib import Path

import orjson
import pytest
from pytest_httpserver import HTTPServer
from typer.testing import CliRunner

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from filbert.cli import app as cli_app  # noqa: E402
from filbert.config import Settings  # noqa: E402
from filbert.server import create_app  # noqa: E402
from tests.conftest import fixture_html  # noqa: E402

NEWS = fixture_html("news.html")
BLOG = fixture_html("blog.html")
KEY = "test-key-123"
AUTH = {"Authorization": f"Bearer {KEY}"}


def make_settings(settings: Settings, tmp_path: Path, **kw) -> Settings:
    base = {
        "api_keys": KEY,
        "api_allow_private_urls": True,  # سرور تست روی 127.0.0.1 است
        "api_jobs_dir": tmp_path / "jobs",
        "respect_robots": False,
        "workers": 1,
    }
    return settings.model_copy(update={**base, **kw})


@pytest.fixture
def client(settings: Settings, tmp_path: Path):
    with TestClient(create_app(make_settings(settings, tmp_path))) as c:
        yield c


def test_health_is_public_and_v1_needs_key(client: TestClient) -> None:
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["auth"] is True
    r = client.post("/v1/extract", json={"html": NEWS})
    assert r.status_code == 401 and r.json()["error"] == "unauthorized"
    assert (
        client.post("/v1/extract", json={"html": NEWS}, headers={"X-API-Key": "nope"}).status_code
        == 401
    )
    assert (
        client.post("/v1/extract", json={"html": NEWS}, headers={"X-API-Key": KEY}).status_code
        == 200
    )


def test_extract_html_with_fields(client: TestClient) -> None:
    r = client.post(
        "/v1/extract",
        headers=AUTH,
        json={
            "html": NEWS,
            "url": "https://example.ir/news/1",
            "fields": ["seo.title", "content.text", "content.chunks"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"seo", "content"} and set(body["seo"]) == {"title"}
    assert body["seo"]["title"].startswith("افزایش قیمت")
    assert body["content"]["text"] and body["content"]["chunks"]
    # یونیکد بدون escape
    assert "افزایش".encode() in r.content


def test_extract_validation_errors(client: TestClient) -> None:
    r = client.post("/v1/extract", headers=AUTH, json={})
    assert r.status_code == 422 and r.json()["error"] == "invalid_request"
    r = client.post("/v1/extract", headers=AUTH, json={"html": NEWS, "fields": ["seo.nope"]})
    assert r.status_code == 422 and r.json()["error"] == "unknown_field"
    r = client.post("/v1/extract", headers=AUTH, json={"html": NEWS, "render": "sometimes"})
    assert r.status_code == 422
    r = client.post("/v1/extract", headers=AUTH, json={"html": NEWS, "unknown_option": 1})
    assert r.status_code == 422


def test_extract_url_and_options(client: TestClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request("/blog").respond_with_data(BLOG, content_type="text/html")
    r = client.post(
        "/v1/extract",
        headers=AUTH,
        json={"url": httpserver.url_for("/blog"), "chunk": False, "digits": "en"},
    )
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["http"]["status"] == 200 and rec["content"]["chunks"] == []
    assert "می‌خواهیم" in rec["content"]["text"]  # ZWNJ حفظ شد
    # دوم بار: کش/ETag مشترک
    again = client.post("/v1/extract", headers=AUTH, json={"url": httpserver.url_for("/blog")})
    assert again.json()["content_hash"] == rec["content_hash"] or again.status_code == 200


def test_extract_upstream_error_and_private_block(
    settings: Settings, tmp_path: Path, httpserver: HTTPServer
) -> None:
    httpserver.expect_request("/missing").respond_with_data("no", status=404)
    with TestClient(create_app(make_settings(settings, tmp_path))) as c:
        r = c.post("/v1/extract", headers=AUTH, json={"url": httpserver.url_for("/missing")})
        assert r.status_code == 502 and r.json()["upstream_status"] == 404
    # تنظیم پیش‌فرض سرور: آدرس داخلی ممنوع
    s = make_settings(settings, tmp_path, api_allow_private_urls=False)
    with TestClient(create_app(s)) as c:
        for url in (httpserver.url_for("/missing"), "http://169.254.169.254/latest/meta-data/"):
            r = c.post("/v1/extract", headers=AUTH, json={"url": url})
            assert r.status_code == 400 and r.json()["error"] == "url_not_allowed", r.text
        r = c.post("/v1/extract", headers=AUTH, json={"url": "file:///etc/passwd"})
        assert r.status_code == 400


def test_batch(client: TestClient, httpserver: HTTPServer) -> None:
    httpserver.expect_request("/a").respond_with_data(NEWS, content_type="text/html")
    httpserver.expect_request("/b").respond_with_data("gone", status=410)
    r = client.post(
        "/v1/extract/batch",
        headers=AUTH,
        json={
            "urls": [httpserver.url_for("/a"), httpserver.url_for("/b")],
            "fields": ["seo.title"],
        },
    )
    body = r.json()
    assert r.status_code == 200 and body["ok"] == 1 and body["failed"] == 1
    a, b = body["results"]
    assert a["ok"] and a["record"] == {"seo": {"title": a["record"]["seo"]["title"]}}
    assert not b["ok"] and b["error"] == "fetch_failed" and b["upstream_status"] == 410


def test_batch_limit(settings: Settings, tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(settings, tmp_path, api_max_batch=2))) as c:
        urls = [f"https://example.ir/{i}" for i in range(3)]
        r = c.post("/v1/extract/batch", headers=AUTH, json={"urls": urls})
        assert r.status_code == 413 and r.json()["error"] == "batch_too_large"


def test_body_size_limit(settings: Settings, tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(settings, tmp_path, api_max_html_bytes=1000))) as c:
        r = c.post("/v1/extract", headers=AUTH, json={"html": "x" * 2000})
        assert r.status_code == 413 and r.json()["error"] == "html_too_large"
        r = c.post("/v1/extract", headers=AUTH, json={"html": "x" * 400_000})
        assert r.status_code == 413 and r.json()["error"] == "request_too_large"


def _wait_job(c: TestClient, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        st = c.get(f"/v1/jobs/{job_id}", headers=AUTH).json()
        if st["status"] not in ("queued", "running"):
            return st
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {st}")


def test_job_lifecycle(client: TestClient, httpserver: HTTPServer) -> None:
    for i in range(3):
        httpserver.expect_request(f"/n{i}").respond_with_data(
            NEWS.replace("افزایش قیمت", f"خبر {i} افزایش قیمت"), content_type="text/html"
        )
    httpserver.expect_request("/sitemap.xml").respond_with_data(
        "<urlset>"
        + "".join(f"<url><loc>{httpserver.url_for(f'/n{i}')}</loc></url>" for i in (1, 2))
        + "</urlset>",
        content_type="application/xml",
    )
    r = client.post(
        "/v1/jobs",
        headers=AUTH,
        json={"urls": [httpserver.url_for("/n0")], "sitemap": httpserver.url_for("/sitemap.xml")},
    )
    assert r.status_code == 202
    job_id = r.json()["id"]
    st = _wait_job(client, job_id)
    assert st["status"] == "done" and st["total"] == 3 and st["stats"]["ok"] == 3

    pages = client.get(f"/v1/jobs/{job_id}/pages", headers=AUTH)
    assert pages.headers["content-type"].startswith("application/x-ndjson")
    recs = [orjson.loads(line) for line in pages.content.splitlines()]
    assert len(recs) == 3 and len({rec["content_hash"] for rec in recs}) == 3
    small = client.get(f"/v1/jobs/{job_id}/pages?fields=seo.title&fields=url", headers=AUTH)
    assert all(set(orjson.loads(x)) == {"seo", "url"} for x in small.content.splitlines())
    chunks = client.get(f"/v1/jobs/{job_id}/chunks", headers=AUTH).content.splitlines()
    assert chunks and "embed_text" in orjson.loads(chunks[0])

    xlsx = client.get(f"/v1/jobs/{job_id}/export.xlsx", headers=AUTH)
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"

    assert any(j["id"] == job_id for j in client.get("/v1/jobs", headers=AUTH).json()["jobs"])
    assert client.delete(f"/v1/jobs/{job_id}", headers=AUTH).status_code == 204
    assert client.get(f"/v1/jobs/{job_id}", headers=AUTH).status_code == 404


def test_job_ids_cannot_escape_jobs_dir(client: TestClient) -> None:
    for bad in ("..", "..%2F..%2Fetc", "20261107-000000-zzzz"):
        assert client.get(f"/v1/jobs/{bad}", headers=AUTH).status_code == 404


def test_job_requires_source(client: TestClient) -> None:
    r = client.post("/v1/jobs", headers=AUTH, json={"limit": 5})
    assert r.status_code == 422
    r = client.post("/v1/jobs", headers=AUTH, json={"urls": ["https://a.ir/"], "pattern": "("})
    assert r.status_code == 422


def test_llm_disabled_by_default(client: TestClient) -> None:
    r = client.post("/v1/llm", headers=AUTH, json={"html": NEWS})
    assert r.status_code == 404 and r.json()["error"] == "llm_disabled"


def test_llm_enabled_with_fake_model(settings: Settings, tmp_path: Path, monkeypatch) -> None:
    from filbert.llm import SeoBrief
    from filbert.llm.extractor import LLMExtractor

    seen: dict = {}

    def fake_extract(self, markdown, schema, *, instructions=None, url=None):
        seen.update(markdown=markdown, schema=schema, url=url)
        return schema(
            suggested_title="عنوان",
            suggested_description="توضیح",
            primary_keyword="بیت‌کوین",
            secondary_keywords=[],
            faq=[],
            content_gaps=[],
        )

    monkeypatch.setattr(LLMExtractor, "extract", fake_extract)
    with TestClient(create_app(make_settings(settings, tmp_path, api_llm=True))) as c:
        r = c.post(
            "/v1/llm",
            headers=AUTH,
            json={"html": NEWS, "url": "https://example.ir/n", "schema": "seo"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["schema"] == "SeoBrief" and r.json()["primary_keyword"] == "بیت‌کوین"
    assert seen["schema"] is SeoBrief and "افزایش قیمت" in seen["markdown"]


def test_open_mode_without_keys(settings: Settings, tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(settings, tmp_path, api_keys=""))) as c:
        assert c.get("/health").json()["auth"] is False
        assert c.post("/v1/extract", json={"html": NEWS}).status_code == 200


def test_openapi_and_cli_serve_help(tmp_path: Path) -> None:
    app = create_app(Settings(api_jobs_dir=tmp_path / "jobs", _env_file=None))
    paths = app.openapi()["paths"]
    assert {"/v1/extract", "/v1/extract/batch", "/v1/jobs", "/v1/jobs/{job_id}/pages"} <= set(paths)
    res = CliRunner().invoke(cli_app, ["serve", "--help"])
    assert res.exit_code == 0 and "--workers" in res.output
