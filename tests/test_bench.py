import pytest

from bench import baselines
from bench.datasets import Dataset, Page
from bench.eval import Aggregate, meta_matches, prf, tokens
from bench.run import check_regression, render_report, run_dataset
from bench.selectors import gold_from_selectors
from tests.conftest import fixture_html


def test_prf_token_level() -> None:
    r = prf("الف ب ج د", "الف ب ج د")
    assert (r.precision, r.recall, r.f1) == (1.0, 1.0, 1.0)
    r = prf("الف ب", "الف ب ج د")
    assert r.recall == 0.5 and r.precision == 1.0 and round(r.f1, 3) == 0.667
    assert prf("", "x").f1 == 0.0 and prf("", "").f1 == 1.0


def test_tokens_normalized() -> None:
    assert tokens("كيف ۱۲") == tokens("کیف 12")
    assert tokens("می‌شود") == ["می‌شود"]


def test_meta_matches() -> None:
    m = meta_matches({"title": " الف  ب ", "author": None}, {"title": "الف ب", "author": "x"})
    assert m["title"] is True and m["author"] is False and m["description"] is None


def test_aggregate_summary() -> None:
    a = Aggregate("x")
    a.add("news", prf("a b c", "a b c"), 1.0)
    a.add("blog", prf("a", "a b c d"), 3.0)
    s = a.summary()
    assert (
        s["n"] == 2
        and s["page_accuracy"] == 0.5
        and s["by_type"]["news"] == 1.0
        and s["p50_ms"] == 2.0
    )


def test_gold_from_selectors_dedup_and_exclude() -> None:
    html = "<html><body><article><h1>ت</h1><div class='c'><p>متن</p><div class='ad'>تبلیغ</div></div></article><script>x</script></body></html>"
    out = gold_from_selectors(html, ["article h1", "article", ".c"], [".ad"])
    assert out == "ت\n\nمتن"  # article شامل h1 است؛ تکرار نشد؛ ad حذف شد


def test_dataset_roundtrip(tmp_path) -> None:
    ds = Dataset("t", root=tmp_path)
    ds.create()
    ds.add_page(
        Page(id="p1", url="https://a.ir/x", type="news", label_status="gold", extra={"k": 1}),
        "<p>سلام</p>",
    )
    ds.put_gold("p1", "سلام", {"title": "س"})
    assert ds.html("p1") == "<p>سلام</p>" and ds.gold_text("p1") == "سلام\n"
    assert ds.pages()[0].extra == {"k": 1} and list(ds.labeled())[0].id == "p1"
    assert ds.summary() == {"news": {"gold": 1}}


def test_run_dataset_on_fixtures_dataset() -> None:
    ds = Dataset("fixtures")
    if not ds.exists():
        pytest.skip("fixtures dataset not built")
    res = run_dataset(
        ds, {"ensemble": baselines.fb_ensemble, "readability": baselines.fb_readability}
    )
    assert res["n_pages"] == 5
    assert res["extractors"]["ensemble"]["f1"] > 0.9
    assert res["meta"]["title"] == 1.0
    report = render_report([res])
    assert "| ensemble |" in report


def test_check_regression() -> None:
    res = {"dataset": "d", "extractors": {"ensemble": {"f1": 0.90, "p50_ms": 2.0}}}
    assert check_regression(res, {"d": {"ensemble": {"f1": 0.91, "p50_ms": 1.0}}})
    assert not check_regression(res, {"d": {"ensemble": {"f1": 0.904, "p50_ms": 1.9}}})


def test_trafilatura_only_in_bench() -> None:
    import subprocess
    import sys

    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, filbert.pipeline, filbert.cli; print('trafilatura' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert out == "False"
    assert baselines.trafilatura_extract(fixture_html("news.html"), "https://x.ir/") != ""
