"""فرمت دیتاست bench:

bench/datasets/<name>/
  index.jsonl              # یک خط به‌ازای هر صفحه: id, url, type, label_status, site, notes
  html/<id>.html.zst       # HTML خام (zstd)
  gold/<id>.txt            # متن اصلی (برچسب)؛ پاراگراف‌ها با خط خالی
  gold/<id>.json           # متادیتای درست: title, description, canonical, published_at, author, lang
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

import zstandard

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
PAGE_TYPES: tuple[str, ...] = ("news", "blog", "product", "landing", "forum", "other")
LABEL_STATUSES: tuple[str, ...] = ("gold", "auto", "silver", "unlabeled")


@dataclass(slots=True)
class Page:
    id: str
    url: str
    type: str = "other"
    label_status: str = "unlabeled"
    site: str = ""
    notes: str = ""
    extra: dict = field(default_factory=dict)

    def to_json(self) -> str:
        d = asdict(self)
        extra = d.pop("extra")
        d.update(extra)
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> Page:
        d = json.loads(line)
        known = {
            k: d.pop(k) for k in ("id", "url", "type", "label_status", "site", "notes") if k in d
        }
        return cls(**known, extra=d)


class Dataset:
    def __init__(self, name: str, root: Path | None = None) -> None:
        self.name = name
        self.root = (root or DATASETS_DIR) / name
        self.html_dir = self.root / "html"
        self.gold_dir = self.root / "gold"
        self.index_path = self.root / "index.jsonl"
        self._zc = zstandard.ZstdCompressor(level=9)
        self._zd = zstandard.ZstdDecompressor()

    def exists(self) -> bool:
        return self.index_path.exists()

    def create(self) -> None:
        self.html_dir.mkdir(parents=True, exist_ok=True)
        self.gold_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.touch()

    def pages(self) -> list[Page]:
        if not self.index_path.exists():
            return []
        out = []
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(Page.from_json(line))
        return out

    def write_index(self, pages: list[Page]) -> None:
        self.index_path.write_text("".join(p.to_json() + "\n" for p in pages), encoding="utf-8")

    def add_page(self, page: Page, html: str) -> None:
        pages = [p for p in self.pages() if p.id != page.id]
        pages.append(page)
        self.write_index(pages)
        self.put_html(page.id, html)

    def put_html(self, page_id: str, html: str) -> None:
        (self.html_dir / f"{page_id}.html.zst").write_bytes(self._zc.compress(html.encode("utf-8")))

    def html(self, page_id: str) -> str:
        return self._zd.decompress((self.html_dir / f"{page_id}.html.zst").read_bytes()).decode(
            "utf-8"
        )

    def gold_text(self, page_id: str) -> str | None:
        p = self.gold_dir / f"{page_id}.txt"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def gold_meta(self, page_id: str) -> dict | None:
        p = self.gold_dir / f"{page_id}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put_gold(self, page_id: str, text: str | None, meta: dict | None) -> None:
        if text is not None:
            (self.gold_dir / f"{page_id}.txt").write_text(text.strip() + "\n", encoding="utf-8")
        if meta is not None:
            (self.gold_dir / f"{page_id}.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

    def labeled(self, statuses: tuple[str, ...] = ("gold", "auto")) -> Iterator[Page]:
        for p in self.pages():
            if p.label_status in statuses and (self.gold_dir / f"{p.id}.txt").exists():
                yield p

    def summary(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for p in self.pages():
            out.setdefault(p.type, {}).setdefault(p.label_status, 0)
            out[p.type][p.label_status] += 1
        return out
