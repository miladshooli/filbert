# filbert HTTP API (docs/API.md)
#   docker build -t filbert .
#   docker run -p 8000:8000 -e FILBERT_API_KEYS=change-me -v filbert-data:/data filbert
# With JS rendering (Chromium, image grows to ~1.5 GB):
#   docker build --build-arg WITH_RENDER=1 -t filbert:render .
FROM python:3.12-slim

ARG WITH_RENDER=0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    FILBERT_CACHE_DIR=/data/cache \
    FILBERT_API_JOBS_DIR=/data/jobs \
    FILBERT_SERVE_HOST=0.0.0.0 \
    FILBERT_SERVE_PORT=8000

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN extras="server,export"; \
    if [ "$WITH_RENDER" = "1" ]; then extras="$extras,render"; fi; \
    pip install ".[$extras]" \
    && if [ "$WITH_RENDER" = "1" ]; then playwright install --with-deps chromium; fi \
    && cd / && rm -rf /build

RUN useradd --create-home --uid 10001 filbert && mkdir -p /data && chown filbert:filbert /data
USER filbert
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('FILBERT_SERVE_PORT', '8000'), timeout=4)"

CMD ["filbert", "serve"]
