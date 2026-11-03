UV ?= uv
RUN ?= uv run --all-extras

.PHONY: install test lint bench bench-update fixtures-dataset

install:
	$(UV) sync --all-extras --group dev

lint:
	$(RUN) ruff check . --fix && $(RUN) ruff format .

test:
	$(RUN) pytest -q

fixtures-dataset:
	$(RUN) python -m bench.make_fixtures_dataset

# قاعده CLAUDE.md: هر تغییر در src/filbert/extract/ باید این را اجرا کند؛ افت > 0.5 F1 یا ۱۰٪ سرعت = خطا
bench:
	$(RUN) python -m bench.run --compare-with trafilatura --repeat 3 --check

bench-update:
	$(RUN) python -m bench.run --compare-with trafilatura --repeat 3 --update-baseline
