"""وضعیت jobهای خزش روی دیسک (`api_jobs_dir/<job_id>/job.json`).

وضعیت روی دیسک است، نه در حافظه: با چند پردازه uvicorn هر پردازه‌ای می‌تواند وضعیت را برگرداند و
خروجی‌ها (`pages.jsonl`، `chunks.jsonl`، `errors.jsonl`، `run.json`) همان قالب `filbert crawl` هستند.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from filbert.out.store import make_run_id

JOB_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4,16}$")
ACTIVE = frozenset({"queued", "running"})


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":  # os.kill(pid, 0) در ویندوز پردازه را می‌بندد؛ فرض: زنده
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    n = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            n += chunk.count(b"\n")
    return n


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)  # پوشه با اولین job ساخته می‌شود

    def dir(self, job_id: str) -> Path | None:
        """مسیر job؛ None اگر شناسه نامعتبر است یا وجود ندارد (جلوی path traversal)."""
        if not JOB_ID_RE.match(job_id):
            return None
        d = self.root / job_id
        return d if (d / "job.json").exists() else None

    def create(self, request: dict[str, Any]) -> str:
        job_id = make_run_id()
        (self.root / job_id).mkdir(parents=True)
        self._write(
            job_id,
            {
                "id": job_id,
                "status": "queued",
                "created_at": now_iso(),
                "request": request,
                "pid": os.getpid(),
            },
        )
        return job_id

    def _write(self, job_id: str, data: dict[str, Any]) -> None:
        d = self.root / job_id
        tmp = d / "job.json.tmp"
        tmp.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        tmp.replace(d / "job.json")

    def read(self, job_id: str) -> dict[str, Any] | None:
        d = self.dir(job_id)
        if d is None:
            return None
        return orjson.loads((d / "job.json").read_bytes())

    def update(self, job_id: str, **fields: Any) -> dict[str, Any]:
        data = self.read(job_id) or {"id": job_id}
        data.update(fields)
        self._write(job_id, data)
        return data

    def status(self, job_id: str) -> dict[str, Any] | None:
        """job.json + پیشرفت زنده؛ job فعالِ پردازه مرده → `interrupted`."""
        data = self.read(job_id)
        if data is None:
            return None
        d = self.root / job_id
        if data.get("status") in ACTIVE:
            pid = data.get("pid")
            if isinstance(pid, int) and pid != os.getpid() and not _pid_alive(pid):
                data["status"] = "interrupted"
            data["progress"] = {
                "ok": _count_lines(d / "pages.jsonl"),
                "failed": _count_lines(d / "errors.jsonl"),
                "total": data.get("total"),
            }
        return data

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        ids = sorted(
            (p.name for p in self.root.iterdir() if p.is_dir() and JOB_ID_RE.match(p.name)),
            reverse=True,
        )
        out: list[dict[str, Any]] = []
        for job_id in ids[:limit]:
            data = self.status(job_id)
            if data is not None:
                out.append(
                    {k: data.get(k) for k in ("id", "status", "created_at", "finished_at", "total")}
                )
        return out

    def delete(self, job_id: str) -> bool:
        d = self.dir(job_id)
        if d is None:
            return False
        shutil.rmtree(d)
        return True
