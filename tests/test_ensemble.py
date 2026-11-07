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


def test_containment_aware_voting() -> None:
    from filbert.extract.blocks import collect_blocks

    tree = parse(
        "<html><body><ul>"
        + "".join(
            f"<li><h2>تیتر {i}</h2><p>{'متن خبر شماره ' + str(i) + ' است. ' * 8}</p></li>"
            for i in range(3)
        )
        + "</ul></body></html>"
    )
    coarse: list[RawBlock] = []
    collect_blocks(tree.body, None, coarse, source="cetd")  # → یک بلوک ul
    assert [b.type for b in coarse] == ["ul"]
    fine: list[RawBlock] = []
    for li in tree.css("li"):
        collect_blocks(li, None, fine, source="readability")  # → h2/p ریز
    assert len(fine) == 6
    res = ensemble.merge(
        tree, {"readability": fine, "cetd": coarse, "dom": list(coarse)}, min_text_chars=50
    )
    assert not res.recall_mode
    assert [b.type for b in res.blocks] == ["h2", "p"] * 3  # ریزها ماندند، ul حذف شد
    assert all(b.votes == 3 for b in res.blocks)
    assert res.confidence == 1.0


def test_cetd_anchor_when_majority_is_thin() -> None:
    from filbert.extract.blocks import collect_blocks

    items = "".join(f"<li><p>مشخصه شماره {i}: مقدار {i}</p></li>" for i in range(10))
    tree = parse(
        f"<html><body><h1>کالا</h1><ul>{items}</ul><p>{'توضیح کوتاه. ' * 20}</p></body></html>"
    )
    all_blocks: list[RawBlock] = []
    collect_blocks(tree.body, None, all_blocks, source="cetd")
    thin = [b for b in all_blocks if b.type == "h1"]  # readability/dom فقط تیتر
    res = ensemble.merge(
        tree, {"readability": list(thin), "cetd": all_blocks, "dom": list(thin)}, min_text_chars=10
    )
    assert res.recall_anchor and "مشخصه شماره 9" in res.text
    # وقتی اکثریت کافی است، لنگر فعال نمی‌شود
    res2 = ensemble.merge(
        tree, {"readability": all_blocks, "cetd": all_blocks, "dom": list(thin)}, min_text_chars=10
    )
    assert not res2.recall_anchor


def test_single_vote_heading_between_certain_blocks_is_kept() -> None:
    long = "این یک پاراگراف واقعی و بلند از بدنه مقاله است که چند جمله دارد و ادامه پیدا می‌کند."
    tree = parse(
        f"<html><body><p>{long}</p><h2>بخش دوم</h2><p>{long} دوم</p><h2>بخش تنها</h2></body></html>"
    )
    xp = ["/html/body/p[1]", "/html/body/h2[1]", "/html/body/p[2]", "/html/body/h2[2]"]
    from filbert.extract.blocks import collect_blocks

    allb: list[RawBlock] = []
    collect_blocks(tree.body, None, allb, source="cetd")
    paras = [b for b in allb if b.type == "p"]
    outs = {"readability": list(paras), "cetd": allb, "dom": list(paras)}
    chosen = ensemble.select(ensemble.vote(outs, doc_order(tree.body), tree.body.mem_id))
    texts = [v.block.text for v in chosen]
    assert "بخش دوم" in texts  # بین دو پاراگراف قطعی
    assert "بخش تنها" not in texts  # بعدش بلوک قطعی نیست
    assert xp


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


def test_drop_containers_keeps_list_when_coverage_low() -> None:
    from filbert.extract.blocks import collect_blocks

    items = "".join(f"<li><p>مشخصه {i}: مقدار {i}</p></li>" for i in range(8))
    tree = parse(f"<html><body><ul>{items}</ul></body></html>")
    coarse: list[RawBlock] = []
    collect_blocks(tree.body, None, coarse, source="cetd")
    fine: list[RawBlock] = []
    collect_blocks(tree.css("li")[0], None, fine, source="readability")  # فقط یک آیتم
    res = ensemble.merge(
        tree, {"readability": fine, "cetd": coarse, "dom": list(coarse)}, min_text_chars=10
    )
    assert [b.type for b in res.blocks] == ["ul"]  # ظرف ماند؛ آیتم تنها حذف شد
    assert "مشخصه 7" in res.text
