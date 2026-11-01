import json

import pytest

from filbert.extract import ensemble
from filbert.extract.blocks import RawBlock, doc_order
from filbert.extract.domtext import parse
from filbert.extract.preclean import preclean
from filbert.extract.rules import load_rules
from tests.conftest import FIXTURES, fixture_html

RULES = load_rules()
FIXTURE_NAMES = ["news", "blog", "product", "landing", "forum"]


def run(name: str) -> ensemble.EnsembleResult:
    tree = parse(fixture_html(f"{name}.html"))
    preclean(tree, RULES.preclean)
    return ensemble.extract(tree, RULES, base_url="https://example.ir/x/")


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_ensemble_meets_fixture_expectations(name: str) -> None:
    exp = json.loads((FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8"))
    res = run(name)
    text = res.text
    missing = [s for s in exp["include"] if s not in text]
    leaked = [s for s in exp["exclude"] if s in text]
    assert not missing, f"{name}: missing {missing}\n---\n{text}"
    assert not leaked, f"{name}: leaked {leaked}\n---\n{text}"
    assert not res.recall_mode and not res.low_confidence, name
    assert res.confidence is not None and res.confidence >= 0.66
    assert set(res.extractors) == set(ensemble.EXTRACTORS)
    assert all(b.votes >= 1 for b in res.blocks)
    assert len(exp["types"]) and set(exp["types"]) <= {b.type for b in res.blocks}


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_document_order(name: str) -> None:
    res = run(name)
    html = fixture_html(f"{name}.html")
    pos = 0
    for b in res.blocks:
        words = b.text.split()
        if not words:
            continue
        i = html.find(words[0][:8], pos)
        assert i >= 0, f"{name}: out of order: {words[0]!r}"
        pos = i


def _blocks(tree, source: str, xpaths: list[str]) -> list[RawBlock]:
    out = []
    for n in tree.body.traverse():
        if not n.is_element_node or n.tag != "p":
            continue
        from filbert.extract.domtext import node_text, xpath_of

        xp = xpath_of(n)
        if xp in xpaths:
            out.append(
                RawBlock(
                    node=n,
                    type="p",
                    text=node_text(n),
                    html=f"<p>{node_text(n)}</p>",
                    xpath=xp,
                    source=source,
                )
            )
    return out


def test_voting_rules() -> None:
    long = "این یک جمله بلند برای پر کردن حفره است که از هشتاد کاراکتر بیشتر می‌شود و ادامه دارد."
    tree = parse(
        "<html><body>"
        "<p>اول</p><p>" + long + "</p><p>سوم</p><p>کوتاه</p><p>" + long + "</p><p>آخر</p>"
        "</body></html>"
    )
    xp = [f"/html/body/p[{i}]" for i in range(1, 7)]
    outputs = {
        "readability": _blocks(tree, "readability", [xp[0], xp[1], xp[2], xp[3], xp[4]]),
        "cetd": _blocks(tree, "cetd", [xp[0], xp[2], xp[5]]),
        "dom": _blocks(tree, "dom", [xp[2], xp[5]]),
    }
    voted = ensemble.vote(outputs, doc_order(tree.body))
    assert [v.votes for v in voted] == [2, 1, 3, 1, 1, 2]
    chosen = ensemble.select(voted)
    # p[2] و p[5]: یک رأی readability، بلند، بین دو بلوک قطعی → پر شدند. p[4]: کوتاه → حذف.
    assert [v.block.xpath for v in chosen] == [xp[0], xp[1], xp[2], xp[4], xp[5]]


def test_recall_fallback_on_short_output() -> None:
    tree = parse("<html><body><p>الف</p><div><p>ب</p></div></body></html>")
    res = ensemble.extract(tree, RULES, min_text_chars=200)
    assert res.recall_mode and res.low_confidence
    assert res.text  # اتحاد همه بلوک‌ها


def test_forced_recall() -> None:
    tree = parse(fixture_html("news.html"))
    preclean(tree, RULES.preclean)
    res = ensemble.extract(tree, RULES, recall=True)
    assert res.recall_mode
    normal = ensemble.extract(tree, RULES)
    assert len(res.blocks) >= len(normal.blocks)


def test_empty() -> None:
    res = ensemble.extract(parse(""), RULES)
    assert res.blocks == [] and res.confidence is None
