"""سرور HTTP filbert (extras `server`): FastAPI روی همان pipeline کتابخانه. راهنما: docs/API.md.

- `POST /v1/extract`: یک URL یا HTML خام → `PageRecord` (همان JSON خروجی CLI).
- `POST /v1/extract/batch`: چند URL همزمان (سقف `api_max_batch`).
- `POST /v1/jobs`: خزش پس‌زمینه از فهرست URL یا سایت‌مپ؛ خروجی NDJSON و Excel.
- `POST /v1/llm`: لایه اختیاری Claude (خاموش به‌طور پیش‌فرض؛ `FILBERT_API_LLM=true`).

منابع (httpx، کش، robots، استخر رندر) یک بار در lifespan ساخته و بین درخواست‌ها مشترک‌اند؛ پس
محدودیت هر دامنه (`per_host_concurrency`) برای همه کاربران با هم اعمال می‌شود. استخراج (CPU) در
thread اجرا می‌شود تا event loop قفل نشود؛ برای چند هسته `filbert serve --workers N`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import tempfile
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import orjson
from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from filbert import __version__
from filbert.config import Settings
from filbert.fetch.cache import Cache
from filbert.fetch.client import Fetcher
from filbert.fetch.guard import URLGuard
from filbert.fetch.robots import RobotsCache
from filbert.models import PageRecord
from filbert.pipeline import (
    PageError,
    PageLoader,
    extract_html,
    extract_job,
    fetch_and_extract,
    open_render_pool,
)
from filbert.server.jobs import ACTIVE, JobStore, now_iso
from filbert.server.schemas import BatchRequest, ExtractRequest, JobRequest, LLMRequest, Options

log = logging.getLogger(__name__)
HTML_PLACEHOLDER_URL = "about:blank"
NDJSON = "application/x-ndjson"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class JSON(Response):
    """پاسخ JSON با orjson (یونیکد بدون escape؛ قاعده CLAUDE.md)."""

    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return orjson.dumps(content)


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.extra = extra

    def body(self) -> dict[str, Any]:
        return {"error": self.code, "detail": self.detail, **self.extra}


def page_error(e: PageError) -> ApiError:
    if e.kind == "blocked":
        return ApiError(400, "url_not_allowed", e.reason)
    if e.kind == "robots":
        return ApiError(422, "robots_disallowed", e.reason)
    return ApiError(502, "fetch_failed", e.reason, upstream_status=e.status)


def project(
    data: dict[str, Any], fields: list[str] | None, *, strict: bool = True
) -> dict[str, Any]:
    """فقط مسیرهای خواسته‌شده (`seo.title`، `content.chunks`)؛ مسیر ناموجود → ApiError 422
    (`strict=False`: نادیده گرفته می‌شود)."""
    if not fields:
        return data
    out: dict[str, Any] = {}
    for path in fields:
        parts = [p for p in path.split(".") if p]
        src: Any = data
        dst = out
        for i, key in enumerate(parts):
            if not isinstance(src, dict) or key not in src:
                if not strict:
                    break
                raise ApiError(422, "unknown_field", f"unknown field: {path}")
            if i == len(parts) - 1:
                dst[key] = src[key]
            else:
                src = src[key]
                nxt = dst.setdefault(key, {})
                if not isinstance(nxt, dict):  # مسیر والد قبلاً کامل انتخاب شده
                    break
                dst = nxt
    return out


class ServerState:
    """منابع مشترک یک پردازه سرور."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings.model_copy(
            update={"block_private_urls": not settings.api_allow_private_urls}
        )
        self.guard = URLGuard(allow_private=settings.api_allow_private_urls)
        self.keys = tuple(k.strip() for k in settings.api_keys.split(",") if k.strip())
        self.jobs = JobStore(settings.api_jobs_dir)
        self.started_at = time.time()
        self.cache: Cache | None = None
        self.fetcher: Fetcher | None = None
        self.loader: PageLoader | None = None
        self.render_pool: Any = None
        self._render_lock = asyncio.Lock()
        self._render_tried = False
        self._job_slots = asyncio.Semaphore(max(1, settings.api_max_running_jobs))
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._llm: Any = None

    async def start(self) -> None:
        s = self.settings
        self.cache = Cache(s.cache_dir)
        self.fetcher = await Fetcher(s, self.cache, guard=self.guard).__aenter__()
        robots = RobotsCache(s.cache_dir) if s.respect_robots else None
        self.loader = PageLoader(s, self.fetcher, self.cache, robots=robots)
        if s.render != "never":
            await self.ensure_render()

    async def stop(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()  # job خودش وضعیت `interrupted` را می‌نویسد
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self.render_pool is not None:
            await self.render_pool.__aexit__(None, None, None)
        if self.fetcher is not None:
            await self.fetcher.__aexit__(None, None, None)
        if self.cache is not None:
            self.cache.close()

    async def ensure_render(self) -> Any:
        async with self._render_lock:
            if not self._render_tried:
                self._render_tried = True
                self.render_pool = await open_render_pool(self.settings, self.guard)
                assert self.loader is not None
                self.loader.render_pool = self.render_pool
        return self.render_pool

    def request_settings(self, opts: Options) -> Settings:
        return self.settings.model_copy(update=opts.overrides())

    async def record_for_url(self, url: str, opts: Options) -> PageRecord:
        assert self.loader is not None
        settings = self.request_settings(opts)
        if settings.render != "never":
            await self.ensure_render()
        try:
            page = await self.loader.load(url, force=opts.force, render=settings.render)
        except PageError as e:
            raise page_error(e) from e
        try:
            return await asyncio.to_thread(extract_job, page.job, settings)
        except Exception as e:  # noqa: BLE001
            log.exception("extract %s failed", url)
            raise ApiError(500, "extract_failed", f"{type(e).__name__}: {e}") from e

    async def record_for_html(self, html: str, url: str | None, opts: Options) -> PageRecord:
        size = len(html.encode("utf-8"))
        if size > self.settings.api_max_html_bytes:
            raise ApiError(
                413, "html_too_large", f"{size} bytes > {self.settings.api_max_html_bytes}"
            )
        return await asyncio.to_thread(
            extract_html,
            html,
            url or HTML_PLACEHOLDER_URL,
            settings=self.request_settings(opts),
            fetched_at=datetime.now(UTC),
        )

    # --- jobs ---
    def start_job(self, req: JobRequest) -> str:
        job_id = self.jobs.create(req.model_dump(mode="json"))
        task = asyncio.create_task(self._run_job(job_id, req))
        self._tasks[job_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(job_id, None))
        return job_id

    async def _run_job(self, job_id: str, req: JobRequest) -> None:
        async with self._job_slots:
            self.jobs.update(job_id, status="running", started_at=now_iso(), pid=os.getpid())
            try:
                urls = list(dict.fromkeys(req.urls))
                cap = min(req.limit, self.settings.api_max_job_urls)
                if req.sitemap and len(urls) < cap:
                    from filbert.fetch.sitemap import urls_from_sitemap

                    assert self.fetcher is not None
                    urls += await urls_from_sitemap(
                        self.fetcher,
                        req.sitemap,
                        limit=cap,
                        pattern=req.pattern,
                        exclude=req.exclude,
                    )
                urls = list(dict.fromkeys(urls))[:cap]
                self.jobs.update(job_id, total=len(urls))
                stats, _ = await fetch_and_extract(
                    urls,
                    settings=self.request_settings(req),
                    out_dir=self.jobs.root,
                    run_id=job_id,
                    formats=(),
                    force=req.force,
                    only_changed=req.only_changed,
                    keep_records=False,
                )
                self.jobs.update(
                    job_id,
                    status="done",
                    finished_at=now_iso(),
                    stats=stats.model_dump(mode="json"),
                )
            except asyncio.CancelledError:
                self.jobs.update(job_id, status="interrupted", finished_at=now_iso())
                raise
            except Exception as e:  # noqa: BLE001
                log.exception("job %s failed", job_id)
                self.jobs.update(
                    job_id,
                    status="failed",
                    finished_at=now_iso(),
                    error=f"{type(e).__name__}: {e}",
                )

    def llm(self) -> Any:
        if self._llm is None:
            from filbert.llm import LLMExtractor

            self._llm = LLMExtractor(cache_dir=self.settings.cache_dir)
        return self._llm


def _state(request: Request) -> ServerState:
    return request.app.state.filbert


def _require_key(request: Request) -> None:
    st = _state(request)
    if not st.keys:
        return
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    token = token or request.headers.get("x-api-key", "").strip()
    if not token or not any(secrets.compare_digest(token, k) for k in st.keys):
        raise ApiError(401, "unauthorized", "missing or invalid API key")


def _ndjson_lines(path: Path, fields: list[str] | None) -> Iterator[bytes]:
    with path.open("rb") as fh:
        for line in fh:
            if not line.strip():
                continue
            if fields:
                yield orjson.dumps(project(orjson.loads(line), fields, strict=False)) + b"\n"
            else:
                yield line if line.endswith(b"\n") else line + b"\n"


def create_app(settings: Settings | None = None) -> FastAPI:
    """کارخانه اپ؛ `uvicorn --factory filbert.server.app:create_app` هم کار می‌کند."""
    settings = settings or Settings()
    state = ServerState(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await state.start()
        if not state.keys:
            log.warning("FILBERT_API_KEYS is empty: the API is open to anyone who can reach it")
        try:
            yield
        finally:
            await state.stop()

    app = FastAPI(
        title="filbert",
        version=__version__,
        summary="Main-content and SEO-metadata extraction, tuned for Persian (Farsi) pages.",
        default_response_class=JSON,
        lifespan=lifespan,
    )
    app.state.filbert = state

    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> Response:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        return JSON(exc.body(), status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_request: Request, exc: RequestValidationError) -> Response:
        errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]
        return JSON({"error": "invalid_request", "detail": errors}, status_code=422)

    origins = [o.strip() for o in settings.api_cors_origins.split(",") if o.strip()]
    if origins:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "X-API-Key", "Content-Type"],
        )

    body_cap = settings.api_max_html_bytes + 256_000

    @app.middleware("http")
    async def _body_limit(request: Request, call_next: Any) -> Response:
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > body_cap:
            return JSON(
                {"error": "request_too_large", "detail": f"body > {body_cap} bytes"},
                status_code=413,
            )
        return await call_next(request)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        return {"name": "filbert", "version": __version__, "docs": "/docs", "health": "/health"}

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "uptime_s": round(time.time() - state.started_at, 1),
            "auth": bool(state.keys),
            "render": state.settings.render,
            "llm": state.settings.api_llm,
        }

    v1 = APIRouter(prefix="/v1", dependencies=[Depends(_require_key)])

    @v1.post("/extract", tags=["extract"])
    async def extract(req: ExtractRequest) -> Response:
        """یک صفحه: `url` (دریافت از وب) یا `html` (بدون شبکه) → PageRecord."""
        if req.html is not None:
            rec = await state.record_for_html(req.html, req.url, req)
        else:
            assert req.url is not None
            rec = await state.record_for_url(req.url, req)
        return JSON(project(rec.model_dump(mode="json"), req.fields))

    @v1.post("/extract/batch", tags=["extract"])
    async def extract_batch(req: BatchRequest) -> Response:
        """چند URL همزمان؛ هر نتیجه جدا `ok` یا `error` دارد."""
        urls = list(dict.fromkeys(req.urls))
        if len(urls) > state.settings.api_max_batch:
            raise ApiError(
                413,
                "batch_too_large",
                f"{len(urls)} urls > {state.settings.api_max_batch}; use /v1/jobs",
            )
        t0 = time.perf_counter()

        async def one(u: str) -> dict[str, Any]:
            try:
                rec = await state.record_for_url(u, req)
            except ApiError as e:
                return {"url": u, "ok": False, **e.body()}
            return {
                "url": u,
                "ok": True,
                "record": project(rec.model_dump(mode="json"), req.fields),
            }

        results = await asyncio.gather(*(one(u) for u in urls))
        return JSON(
            {
                "results": results,
                "ok": sum(1 for r in results if r["ok"]),
                "failed": sum(1 for r in results if not r["ok"]),
                "took_ms": int((time.perf_counter() - t0) * 1000),
            }
        )

    @v1.post("/jobs", tags=["jobs"], status_code=202)
    async def create_job(req: JobRequest) -> Response:
        """خزش پس‌زمینه (فهرست URL و/یا سایت‌مپ). وضعیت: `GET /v1/jobs/{id}`."""
        if len(req.urls) > state.settings.api_max_job_urls:
            raise ApiError(
                413, "job_too_large", f"{len(req.urls)} urls > {state.settings.api_max_job_urls}"
            )
        job_id = state.start_job(req)
        return JSON(
            {"id": job_id, "status": "queued", "status_url": f"/v1/jobs/{job_id}"},
            status_code=202,
        )

    @v1.get("/jobs", tags=["jobs"])
    async def list_jobs(limit: Annotated[int, Query(ge=1, le=500)] = 50) -> Response:
        return JSON({"jobs": state.jobs.list(limit)})

    def _job_or_404(job_id: str) -> dict[str, Any]:
        data = state.jobs.status(job_id)
        if data is None:
            raise ApiError(404, "job_not_found", job_id)
        return data

    @v1.get("/jobs/{job_id}", tags=["jobs"])
    async def get_job(job_id: str) -> Response:
        return JSON(_job_or_404(job_id))

    def _job_file(job_id: str, name: str) -> Path:
        _job_or_404(job_id)
        path = state.jobs.root / job_id / name
        if not path.exists():
            raise ApiError(404, "not_ready", f"{name} not written yet")
        return path

    @v1.get("/jobs/{job_id}/pages", tags=["jobs"])
    async def job_pages(
        job_id: str, fields: Annotated[list[str] | None, Query()] = None
    ) -> Response:
        """NDJSON: یک PageRecord در هر خط (با `?fields=seo&fields=content.text` کوچک‌تر)."""
        path = _job_file(job_id, "pages.jsonl")
        return StreamingResponse(_ndjson_lines(path, fields), media_type=NDJSON)

    @v1.get("/jobs/{job_id}/chunks", tags=["jobs"])
    async def job_chunks(job_id: str) -> Response:
        return StreamingResponse(
            _ndjson_lines(_job_file(job_id, "chunks.jsonl"), None), media_type=NDJSON
        )

    @v1.get("/jobs/{job_id}/errors", tags=["jobs"])
    async def job_errors(job_id: str) -> Response:
        return StreamingResponse(
            _ndjson_lines(_job_file(job_id, "errors.jsonl"), None), media_type=NDJSON
        )

    @v1.get("/jobs/{job_id}/export.xlsx", tags=["jobs"])
    async def job_excel(job_id: str, chunks: bool = True) -> Response:
        """Excel پنل سئو (pages/issues/headings/links/images/chunks)؛ نیاز به extras export."""
        if _job_or_404(job_id)["status"] in ACTIVE:
            raise ApiError(409, "job_running", "wait until the job is done")
        try:
            from filbert.out.excel import export_xlsx
        except ImportError as e:
            raise ApiError(501, "export_unavailable", "install the export extra") from e
        fd, tmp = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        await asyncio.to_thread(
            export_xlsx, state.jobs.root / job_id, Path(tmp), include_chunks=chunks
        )
        return FileResponse(
            tmp,
            media_type=XLSX,
            filename=f"filbert-{job_id}.xlsx",
            background=BackgroundTask(os.unlink, tmp),
        )

    @v1.delete("/jobs/{job_id}", tags=["jobs"], status_code=204)
    async def delete_job(job_id: str) -> Response:
        if _job_or_404(job_id)["status"] in ACTIVE:
            raise ApiError(409, "job_running", "job is still running")
        state.jobs.delete(job_id)
        return Response(status_code=204)

    @v1.post("/llm", tags=["llm"])
    async def llm(req: LLMRequest) -> Response:
        """استخراج ساختاریافته با Claude از Markdown تمیز (`schema`: article | seo)."""
        if not state.settings.api_llm:
            raise ApiError(404, "llm_disabled", "set FILBERT_API_LLM=true on the server")
        from filbert.llm import SCHEMAS, LLMUnavailable

        opts = Options()
        if req.html is not None:
            rec = await state.record_for_html(req.html, req.url, opts)
        else:
            assert req.url is not None
            rec = await state.record_for_url(req.url, opts)
        schema = SCHEMAS[req.schema_name]
        ex = state.llm()
        try:
            result = await asyncio.to_thread(
                ex.extract,
                rec.content.markdown or rec.content.text or "",
                schema,
                instructions=req.instructions,
                url=rec.final_url or rec.url,
            )
        except LLMUnavailable as e:
            raise ApiError(502, "llm_failed", str(e)) from e
        return JSON(
            {
                "url": rec.final_url or rec.url,
                "schema": schema.__name__,
                "model": ex.model,
                **result.model_dump(mode="json"),
            }
        )

    app.include_router(v1)
    return app
