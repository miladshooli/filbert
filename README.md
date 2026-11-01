# filbert

ابزار استخراج محتوای وب با دقت و سرعت بالا، بهینه برای فارسی.
طراحی کامل: [docs/BLUEPRINT.md](docs/BLUEPRINT.md) · راهنمای Claude Code: [CLAUDE.md](CLAUDE.md)

## شروع
```powershell
uv sync --all-extras
uv run pytest -q
uv run filbert extract https://example.ir --out out/ --formats json,html,md
```
