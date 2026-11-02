from pathlib import Path

import pytest

from filbert.config import Settings
from filbert.extract.domscore import FEATURE_ORDER, Features, load_dom_model
from filbert.pipeline import extract_html
from tests.conftest import fixture_html

MODEL = Path("data/models/dom_lgbm.pkl")


def test_loader_handles_missing_and_bad_paths(tmp_path: Path) -> None:
    load_dom_model.cache_clear()
    assert load_dom_model(None) is None
    assert load_dom_model(str(tmp_path / "nope.pkl")) is None


def test_feature_order_matches_features() -> None:
    f = Features(*([0.0] * (len(FEATURE_ORDER) - 1)))
    assert [k for k in FEATURE_ORDER if not hasattr(f, k)] == []


@pytest.mark.skipif(not MODEL.exists(), reason="trained model not present")
def test_model_runs_through_pipeline() -> None:
    load_dom_model.cache_clear()
    pytest.importorskip("joblib")
    m = load_dom_model(str(MODEL))
    if m is None:
        pytest.skip("sklearn/joblib not installed")
    settings = Settings(dom_model_path=MODEL, _env_file=None)
    rec = extract_html(fixture_html("news.html"), "https://news.example.ir/x/", settings=settings)
    assert rec.content.word_count and rec.content.word_count > 100
    assert "readability" in rec.content.extractors and rec.content.extractors["dom"] >= 0
