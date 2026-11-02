import json

from filbert.chunk import ChunkOptions, chunk_blocks
from filbert.chunk.sentence import ends_at_boundary, split_sentences
from filbert.models import Block
from filbert.pipeline import extract_html
from tests.conftest import fixture_html


def test_sentence_splitter_persian_cases() -> None:
    assert split_sentences("سلام دنیا. این جمله دوم است؟ بله! و سومی…") == [
        "سلام دنیا.",
        "این جمله دوم است؟",
        "بله!",
        "و سومی…",
    ]
    assert split_sentences("قیمت ۳.۵ درصد رشد کرد. نرخ 2.75 ثابت ماند.") == [
        "قیمت ۳.۵ درصد رشد کرد.",
        "نرخ 2.75 ثابت ماند.",
    ]
    assert split_sentences("ر.ک. به بخش دوم. سپس ادامه دهید.") == [
        "ر.ک. به بخش دوم.",
        "سپس ادامه دهید.",
    ]
    assert split_sentences("به سایت https://nobitex.ir/mag/x.html مراجعه کنید. ممنون.") == [
        "به سایت https://nobitex.ir/mag/x.html مراجعه کنید.",
        "ممنون.",
    ]
    assert split_sentences("او گفت: «می‌شود.» و رفت.") == ["او گفت: «می‌شود.»", "و رفت."]
    assert split_sentences("خط اول\nخط دوم بدون نقطه") == ["خط اول", "خط دوم بدون نقطه"]
    assert split_sentences("الف؛ ب: ج.") == ["الف؛ ب: ج."]
    assert split_sentences("الف؛ ب: ج.", soft=True) == ["الف؛", "ب:", "ج."]
    assert split_sentences("") == []
    # ZWNJ هرگز شکسته نمی‌شود
    out = split_sentences("کتاب‌ها را می‌خوانیم. می‌شود.")
    assert out == ["کتاب‌ها را می‌خوانیم.", "می‌شود."] and all("‌" in s for s in out)


def test_ends_at_boundary() -> None:
    assert ends_at_boundary("جمله.") and ends_at_boundary("پرسش؟»") and ends_at_boundary("")
    assert not ends_at_boundary("نیمه")


def _p(text: str, xp: str = "/html/body/p[1]") -> Block:
    return Block(type="p", text=text, html=f"<p>{text}</p>", xpath=xp)


def _h(level: int, text: str) -> Block:
    return Block(
        type=f"h{level}",
        text=text,
        html=f"<h{level}>{text}</h{level}>",
        xpath=f"/html/body/h{level}[1]",
    )


def test_structural_sections_and_budget() -> None:
    para = " ".join(["این یک جمله آزمایشی نسبتاً بلند برای سنجش بودجه است."] * 6)  # ~60 کلمه
    blocks = [
        _h(1, "تیتر صفحه"),
        _p(para, "/p[1]"),
        _h(2, "بخش اول"),
        _p(para, "/p[2]"),
        _p(para, "/p[3]"),
        _p(para, "/p[4]"),
        _h(3, "زیربخش"),
        _p(para, "/p[5]"),
        _h(2, "بخش دوم"),
        _p("کوتاه.", "/p[6]"),
    ]
    chunks = chunk_blocks(
        blocks, opts=ChunkOptions(max_units=130, hard_max=200, overlap_sentences=1)
    )
    paths = [c.heading_path for c in chunks]
    assert paths[0] == [] and ["بخش اول"] in paths and ["بخش اول", "زیربخش"] in paths
    # بخش ریز («کوتاه.») با چانک قبلی ادغام می‌شود؛ هدینگش داخل متن می‌ماند
    assert ["بخش دوم"] not in paths and "بخش دوم\n\nکوتاه." in chunks[-1].text_raw
    assert all(c.word_count <= 200 for c in chunks)
    first_sec = [c for c in chunks if c.heading_path == ["بخش اول"]]
    assert len(first_sec) == 2  # ۳ پاراگراف ۶۰ کلمه‌ای با بودجه ۱۳۰ → ۲ چانک
    assert first_sec[0].text_raw.startswith("بخش اول\n\n")  # هدینگ در اولین چانک بخش
    assert first_sec[1].overlap_words > 0 and first_sec[1].text_raw.startswith(
        "این یک جمله"
    )  # هم‌پوشانی جمله‌ای
    assert chunks[0].embed_text.startswith("تیتر صفحه\n\n")
    assert first_sec[0].embed_text.startswith("تیتر صفحه › بخش اول\n\n")
    assert [c.index for c in chunks] == list(range(len(chunks))) and chunks[-1].position <= 1.0


def test_long_paragraph_split_on_sentences_and_atomic_blocks() -> None:
    long = " ".join(f"جمله شماره {i} که حدود ده کلمه دارد و با نقطه تمام می‌شود." for i in range(40))
    table = "\n\n".join(["مدل\nقیمت"] + [f"ردیف {i}\n{i * 1000}" for i in range(1, 80)])
    blocks = [
        _p(long, "/p[1]"),
        Block(type="table", text=table, html="<table></table>", xpath="/table[1]"),
        Block(type="pre", text="x = 1\n" * 300, html="<pre></pre>", xpath="/pre[1]"),
    ]
    chunks = chunk_blocks(
        blocks, opts=ChunkOptions(max_units=100, hard_max=150, overlap_sentences=0)
    )
    para_chunks = [c for c in chunks if c.block_types == ["p"]]
    assert all(c.text_raw.rstrip().endswith(".") for c in para_chunks) and len(para_chunks) >= 4
    table_chunks = [c for c in chunks if c.block_types == ["table"]]
    assert len(table_chunks) >= 2 and all(
        c.text_raw.startswith("مدل\nقیمت") for c in table_chunks
    )  # تکرار سطر عنوان
    pre = [c for c in chunks if c.block_types == ["pre"]]
    assert pre and all(c.word_count <= 150 for c in pre)  # کد بلند روی خط تقسیم می‌شود، نه وسط خط
    assert all(ln.strip() == "x = 1" for c in pre for ln in c.text_raw.splitlines() if ln.strip())


def test_broken_heading_hierarchy_and_list_intro() -> None:
    para = "متن بخش با چند کلمه. جمله دوم."
    blocks = [
        _h(1, "تیتر"),
        _h(4, "اولین بخش با h4"),
        _p(para, "/p[1]"),
        _h(1, "h1 دوم که باید سطح ۱ باشد"),
        _p(para, "/p[2]"),
        _h(2, "x" * 200),
        _p(para, "/p[3]"),
        _h(2, "هدینگ خالی"),
        _h(2, "هدینگ پر"),
        _p("موارد زیر:", "/p[4]"),
        Block(type="ul", text="یک\nدو\nسه", html="<ul></ul>", xpath="/ul[1]"),
    ]
    chunks = chunk_blocks(blocks, opts=ChunkOptions(max_units=50, hard_max=80))
    paths = [tuple(c.heading_path) for c in chunks]
    assert ("اولین بخش با h4",) in paths  # h4 → سطح مؤثر ۱
    assert ("h1 دوم که باید سطح ۱ باشد",) in paths
    assert not any("x" * 200 in p for path in paths for p in path)  # هدینگ خیلی بلند مرز نیست
    assert not any("هدینگ خالی" in p for p in paths)  # بخش خالی حذف شد
    # بخش «هدینگ پر» (۵ کلمه) با چانک قبلی ادغام شده؛ فهرست با جمله معرفش یک‌جا می‌ماند
    last = chunks[-1]
    assert "هدینگ پر" in last.text_raw and "موارد زیر:" in last.text and "سه" in last.text
    assert last.text_raw.index("موارد زیر:") < last.text_raw.index("سه")


def test_pipeline_chunks_and_jsonl(tmp_path) -> None:
    rec = extract_html(fixture_html("blog.html"), "https://blog.example.ir/x/")
    chunks = rec.content.chunks
    assert chunks and all(c.word_count > 0 for c in chunks)
    assert any(c.heading_path == ["کیف پول سخت‌افزاری چیست؟"] for c in chunks)
    assert all("‌" in c.text or "‌" not in c.text_raw for c in chunks)
    assert chunks[0].embed_text.startswith("چطور کیف پول سخت‌افزاری بخریم؟")
    data = json.loads(rec.model_dump_json())
    assert data["content"]["chunks"][0]["id"].startswith("000-")
    from filbert.out.store import Store

    st = Store(tmp_path, run_id="c1", formats=("json",))
    st.write(rec)
    st.close()
    lines = (tmp_path / "c1" / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(chunks) and json.loads(lines[0])["url"] == "https://blog.example.ir/x/"
