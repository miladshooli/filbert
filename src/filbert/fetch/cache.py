"""کش دو سطحی: ایندکس SQLite (WAL) برای ETag/Last-Modified و ذخیره HTML خام فشرده با zstd.

کلید هر صفحه = sha256 آدرس نرمال‌شده. فایل خام در `cache/raw/<sha256>.html.zst`.
"""

from __future__ import annotations

import hashlib
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import zstandard

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    url TEXT PRIMARY KEY,
    final_url TEXT,
    status INTEGER,
    etag TEXT,
    last_modified TEXT,
    content_type TEXT,
    encoding TEXT,
    fetched_at TEXT NOT NULL,
    content_hash TEXT,
    run_id TEXT,
    raw_key TEXT NOT NULL,
    rendered INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass(slots=True)
class CacheEntry:
    url: str
    raw_key: str
    fetched_at: datetime
    final_url: str | None = None
    status: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    content_type: str | None = None
    encoding: str | None = None
    content_hash: str | None = None
    run_id: str | None = None
    rendered: bool = False


def raw_key_for(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


class RawStore:
    """HTML خام فشرده با zstd روی دیسک."""

    def __init__(self, root: Path, level: int = 6) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._c = zstandard.ZstdCompressor(level=level)
        self._d = zstandard.ZstdDecompressor()

    def path(self, key: str) -> Path:
        return self.root / f"{key}.html.zst"

    def put(self, key: str, data: bytes) -> Path:
        p = self.path(key)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(self._c.compress(data))
        tmp.replace(p)
        return p

    def get(self, key: str) -> bytes | None:
        p = self.path(key)
        if not p.exists():
            return None
        return self._d.decompress(p.read_bytes())

    def exists(self, key: str) -> bool:
        return self.path(key).exists()


class CacheIndex:
    """ایندکس SQLite با WAL."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self.path, isolation_level=None, check_same_thread=False, timeout=30.0
        )
        # چند پردازه (`filbert serve --workers N`) هم‌زمان پایگاه تازه را باز می‌کنند؛ تغییر
        # journal_mode قفل انحصاری می‌خواهد و busy handler SQLite برایش صبر نمی‌کند → تلاش مجدد.
        for attempt in range(50):
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
                self._conn.executescript(_SCHEMA)
                break
            except sqlite3.OperationalError as e:
                if "locked" not in str(e) or attempt == 49:
                    raise
                time.sleep(0.05 + random.random() * 0.1)

    def get(self, url: str) -> CacheEntry | None:
        row = self._conn.execute(
            "SELECT url, raw_key, fetched_at, final_url, status, etag, last_modified, content_type,"
            " encoding, content_hash, run_id, rendered FROM pages WHERE url = ?",
            (url,),
        ).fetchone()
        if row is None:
            return None
        return CacheEntry(
            url=row[0],
            raw_key=row[1],
            fetched_at=datetime.fromisoformat(row[2]),
            final_url=row[3],
            status=row[4],
            etag=row[5],
            last_modified=row[6],
            content_type=row[7],
            encoding=row[8],
            content_hash=row[9],
            run_id=row[10],
            rendered=bool(row[11]),
        )

    def put(self, e: CacheEntry) -> None:
        self._conn.execute(
            "INSERT INTO pages (url, raw_key, fetched_at, final_url, status, etag, last_modified,"
            " content_type, encoding, content_hash, run_id, rendered)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(url) DO UPDATE SET raw_key=excluded.raw_key, fetched_at=excluded.fetched_at,"
            " final_url=excluded.final_url, status=excluded.status, etag=excluded.etag,"
            " last_modified=excluded.last_modified, content_type=excluded.content_type,"
            " encoding=excluded.encoding, content_hash=COALESCE(excluded.content_hash, pages.content_hash),"
            " run_id=COALESCE(excluded.run_id, pages.run_id),"
            " rendered=excluded.rendered",
            (
                e.url,
                e.raw_key,
                e.fetched_at.isoformat(timespec="seconds"),
                e.final_url,
                e.status,
                e.etag,
                e.last_modified,
                e.content_type,
                e.encoding,
                e.content_hash,
                e.run_id,
                int(e.rendered),
            ),
        )

    def update_hash(self, url: str, content_hash: str, run_id: str | None) -> None:
        self._conn.execute(
            "UPDATE pages SET content_hash = ?, run_id = ? WHERE url = ?",
            (content_hash, run_id, url),
        )

    def touch(self, url: str, fetched_at: datetime) -> None:
        self._conn.execute(
            "UPDATE pages SET fetched_at = ? WHERE url = ?",
            (fetched_at.isoformat(timespec="seconds"), url),
        )

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0])

    def close(self) -> None:
        self._conn.close()


class Cache:
    """ترکیب ایندکس و ذخیره خام؛ یک نمونه به‌ازای هر `cache_dir`."""

    def __init__(self, cache_dir: Path) -> None:
        self.dir = Path(cache_dir)
        self.raw = RawStore(self.dir / "raw")
        self.index = CacheIndex(self.dir / "index.sqlite")

    def lookup(self, url: str) -> CacheEntry | None:
        e = self.index.get(url)
        if e is not None and not self.raw.exists(e.raw_key):
            return None  # ایندکس بدون فایل خام → نامعتبر
        return e

    def store(
        self,
        url: str,
        body: bytes,
        *,
        final_url: str | None,
        status: int | None,
        headers: dict[str, str],
        encoding: str | None,
        rendered: bool = False,
        fetched_at: datetime | None = None,
    ) -> CacheEntry:
        key = raw_key_for(url)
        self.raw.put(key, body)
        entry = CacheEntry(
            url=url,
            raw_key=key,
            fetched_at=fetched_at or datetime.now(UTC),
            final_url=final_url,
            status=status,
            etag=headers.get("etag"),
            last_modified=headers.get("last-modified"),
            content_type=headers.get("content-type"),
            encoding=encoding,
            rendered=rendered,
        )
        self.index.put(entry)
        return entry

    def raw_ref(self, key: str) -> str:
        """مسیر نسبی برای فیلد `raw_html_ref` (ویندوزسازگار، با `/`)."""
        return (Path(self.dir.name) / "raw" / f"{key}.html.zst").as_posix()

    def close(self) -> None:
        self.index.close()
