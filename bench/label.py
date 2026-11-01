"""ابزار برچسب‌زنی: یک صفحه HTML مستقل با فهرست بلوک‌های کاندید صفحه (از درخت خام، بدون preclean)؛
بلوک‌هایی که در برچسب فعلی (auto/gold) هستند از قبل تیک دارند. دکمه «دانلود» فایل `<id>.txt` و `<id>.json`
را می‌سازد که باید در `gold/` کپی شود و `label_status` در `index.jsonl` به `gold` تغییر کند
(یا `python -m bench.label <dataset> --promote <id>` پس از کپی).

    python -m bench.label fa-200 <id> [<id> ...] | --all [--status unlabeled,auto]
"""

from __future__ import annotations

import argparse
import html as _html
import json
import sys

from bench.datasets import Dataset
from filbert.extract.blocks import iter_candidate_blocks
from filbert.extract.domtext import node_text, parse, xpath_of
from filbert.meta.head import extract_head

_PAGE = """<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<title>برچسب‌زنی {id}</title>
<style>
body{{font-family:system-ui,Tahoma;max-width:1100px;margin:0 auto;padding:16px;line-height:1.9;background:#fafafa}}
.b{{border:1px solid #ddd;border-radius:8px;padding:8px 12px;margin:6px 0;background:#fff;display:flex;gap:10px;align-items:flex-start}}
.b.on{{background:#e9f7ec;border-color:#8fcf9b}} .b input{{margin-top:10px}} .t{{flex:1;white-space:pre-wrap}}
.m{{font-size:11px;color:#777;font-family:monospace;direction:ltr;text-align:left}}
.bar{{position:sticky;top:0;background:#fff;padding:8px;border-bottom:1px solid #ddd;display:flex;gap:8px;align-items:center;z-index:9}}
textarea{{width:100%;min-height:60px}} label.f{{display:block;margin:4px 0}} input.meta{{width:100%}}
</style></head><body>
<div class="bar"><b>{id}</b> · {type} · <a href="{url}" target="_blank">صفحه اصلی</a>
<button onclick="dl()">دانلود txt + json</button><button onclick="toggle(true)">همه</button><button onclick="toggle(false)">هیچ</button>
<span id="n"></span></div>
<h3>متادیتا</h3>
{meta_fields}
<h3>بلوک‌ها (محتوای اصلی را تیک بزنید)</h3>
{blocks}
<script>
const id={id_json};
function upd(){{document.querySelectorAll('.b').forEach(b=>b.classList.toggle('on',b.querySelector('input').checked));
 document.getElementById('n').textContent=document.querySelectorAll('.b input:checked').length+' بلوک';}}
function toggle(v){{document.querySelectorAll('.b input').forEach(i=>i.checked=v);upd();}}
document.querySelectorAll('.b input').forEach(i=>i.addEventListener('change',upd));upd();
function save(name,text){{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{{type:'text/plain;charset=utf-8'}}));a.download=name;a.click();}}
function dl(){{const parts=[...document.querySelectorAll('.b')].filter(b=>b.querySelector('input').checked).map(b=>b.querySelector('.t').textContent.trim());
 save(id+'.txt',parts.join('\\n\\n')+'\\n');
 const meta={{}};document.querySelectorAll('input.meta').forEach(i=>{{meta[i.name]=i.value.trim()||null;}});
 save(id+'.json',JSON.stringify(meta,null,2)+'\\n');}}
</script></body></html>"""


def render(ds: Dataset, pid: str) -> str:
    page = next(p for p in ds.pages() if p.id == pid)
    html = ds.html(pid)
    tree = parse(html)
    seo = extract_head(tree, page.url)
    gold = ds.gold_text(pid) or ""
    gold_meta = ds.gold_meta(pid) or {}
    blocks_html: list[str] = []
    for node, tag in iter_candidate_blocks(tree.body):
        text = node_text(node)
        if not text or len(text) < 2:
            continue
        checked = " checked" if text and text in gold else ""
        blocks_html.append(
            f'<div class="b"><input type="checkbox"{checked}><div class="t"><div class="m">{tag} · {_html.escape(xpath_of(node))}</div>'
            f"{_html.escape(text)}</div></div>"
        )
    fields = []
    for name, default in (
        ("title", gold_meta.get("title", seo.title)),
        ("description", gold_meta.get("description", seo.description)),
        ("canonical", gold_meta.get("canonical", seo.canonical)),
        ("published_at", gold_meta.get("published_at")),
        ("author", gold_meta.get("author")),
    ):
        fields.append(
            f'<label class="f">{name}<input class="meta" name="{name}" value="{_html.escape(default or "", quote=True)}"></label>'
        )
    return _PAGE.format(
        id=_html.escape(pid),
        id_json=json.dumps(pid),
        type=page.type,
        url=_html.escape(page.url, quote=True),
        meta_fields="\n".join(fields),
        blocks="\n".join(blocks_html),
    )


def promote(ds: Dataset, pid: str) -> None:
    if ds.gold_text(pid) is None:
        raise SystemExit(f"gold/{pid}.txt not found")
    pages = ds.pages()
    for p in pages:
        if p.id == pid:
            p.label_status = "gold"
    ds.write_index(pages)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--status", default="unlabeled,auto")
    ap.add_argument(
        "--promote", action="store_true", help="idهای داده‌شده را gold علامت بزن (پس از کپی فایل‌ها)"
    )
    args = ap.parse_args()
    ds = Dataset(args.dataset)
    if args.promote:
        for pid in args.ids:
            promote(ds, pid)
        print("promoted:", args.ids)
        return
    ids = args.ids
    if args.all:
        statuses = set(args.status.split(","))
        ids = [p.id for p in ds.pages() if p.label_status in statuses]
    out_dir = ds.root / "label"
    out_dir.mkdir(exist_ok=True)
    for pid in ids:
        (out_dir / f"{pid}.html").write_text(render(ds, pid), encoding="utf-8")
    print(f"{len(ids)} label pages → {out_dir}")


if __name__ == "__main__":
    sys.exit(main())
