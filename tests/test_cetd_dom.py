import json

import pytest

from filbert.extract import cetd, domscore
from filbert.extract.domtext import node_text, parse
from filbert.extract.preclean import preclean
from filbert.extract.rules import load_rules
from tests.conftest import FIXTURES, fixture_html

RULES = load_rules()
FIXTURE_NAMES = ["news", "blog", "product", "landing", "forum"]


def prepared(name: str):
    tree = parse(fixture_html(f"{name}.html"))
    preclean(tree, RULES.preclean)
    return tree


def expectations(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8"))


def test_cetd_stats_simple() -> None:
    t = parse(
        "<html><body><div><p>" + "الف " * 50 + "</p><a href='/x'>لینک</a></div></body></html>"
    )
    stats = cetd.compute_stats(t.body)
    body = stats[t.body.mem_id]
    assert body.link_chars == 4 and body.link_tags == 1
    assert body.chars == 50 * 3 + 49 + 4  # «الف» ×۵۰ با فاصله‌های میانی + «لینک»
    assert body.tags == 3  # div, p, a
    cetd.score(t.body, stats)
    p = t.css_first("p")
    nav = t.css_first("a")
    assert stats[p.mem_id].ctd > stats[nav.mem_id].ctd


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_cetd_recall_on_main_body(name: str) -> None:
    """CETD باید بدنه اصلی را بگیرد (recall)؛ precision کار ensemble است."""
    res = cetd.extract(prepared(name), base_url="https://example.ir/")
    exp = expectations(name)
    text = res.text
    core = [s for s in exp["include"] if len(s) > 25]  # جملات بلند بدنه
    missing = [s for s in core if s not in text]
    assert len(missing) <= max(1, len(core) // 4), f"{name}: {missing}"
    assert res.threshold >= 0 and res.max_density_xpath


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_dom_recall_on_main_body(name: str) -> None:
    res = domscore.extract(prepared(name), RULES.readability, base_url="https://example.ir/")
    exp = expectations(name)
    text = res.text
    core = [s for s in exp["include"] if len(s) > 25]
    missing = [s for s in core if s not in text]
    assert len(missing) <= max(1, len(core) // 4), f"{name}: {missing}"
    assert res.scored > len(res.blocks) > 0


@pytest.mark.parametrize("name", ["news", "blog"])
def test_cetd_and_dom_drop_obvious_boilerplate(name: str) -> None:
    exp = expectations(name)
    for mod, res in (
        ("cetd", cetd.extract(prepared(name))),
        ("dom", domscore.extract(prepared(name), RULES.readability)),
    ):
        leaked = [s for s in exp["exclude"] if s in res.text]
        assert len(leaked) <= 2, f"{mod}/{name}: {leaked}"


def test_dom_features_shape() -> None:
    t = parse(
        "<html><body><div class='post-content'><p>"
        + "جمله. " * 30
        + "</p><ul><li><a href='/a'>الف</a></li></ul></div></body></html>"
    )
    cands = domscore.iter_candidate_blocks(t.body)
    texts = [node_text(n) for n, _ in cands]
    feats = domscore.compute_features(cands, texts, RULES.readability)
    assert len(feats) == 2
    p, ul = feats
    assert 0.5 < p.length < 1.0 and p.punct == 3 and p.class_pos > 0 and p.link_ratio == 0
    assert ul.link_ratio == 1.0 and ul.list_or_table == 1.0
    assert (
        domscore.linear_score(p, domscore.DEFAULT_WEIGHTS)
        > 0
        > domscore.linear_score(ul, domscore.DEFAULT_WEIGHTS)
    )


def test_empty_pages() -> None:
    assert cetd.extract(parse("")).blocks == []
    assert domscore.extract(parse("<html><body></body></html>"), RULES.readability).blocks == []
