UV ?= uv

.PHONY: install test lint bench bench-update fixtures-dataset

install:
	$(UV) sync --all-extras --group dev

lint:
	$(UV) run ruff check . --fix && $(UV) run ruff format .

test:
	$(UV) run pytest -q

fixtures-dataset:
	$(UV) run python -m bench.make_fixtures_dataset

# قاعده CLAUDE.md: هر تغییر در src/filbert/extract/ باید این را اجرا کند؛ افت > 0.5 F1 یا ۱۰٪ سرعت = خطا
bench:
	$(UV) run python -m bench.run --compare-with trafilatura --repeat 3 --check

bench-update:
	$(UV) run python -m bench.run --compare-with trafilatura --repeat 3 --update-baseline
