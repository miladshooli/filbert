from pathlib import Path

import pytest

from filbert.config import Settings
from filbert.fetch.cache import Cache

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def httpserver_listen_address() -> tuple[str, int]:
    # `localhost` روی macOS به ::1 می‌رود و سرور تست روی IPv4 است؛ صریح IPv4.
    return ("127.0.0.1", 0)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        cache_dir=tmp_path / "cache",
        retry_backoff=(0.05, 0.1, 0.2),
        per_host_delay_ms=0,
        connect_timeout=2.0,
        read_timeout=0.6,
        total_timeout=3.0,
        http2=False,
        _env_file=None,
    )


@pytest.fixture
def cache(settings: Settings) -> Cache:
    c = Cache(settings.cache_dir)
    yield c
    c.close()


def fixture_html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
