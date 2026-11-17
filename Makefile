PY ?= python3

.PHONY: bench install lint test check

install:
	$(PY) -m pip install -e '.[dev]'

lint:
	ruff check .
	ruff format --check .
	$(PY) scripts/check.py
	$(PY) -m mypy

test:
	$(PY) -m pytest -q

check: lint test

bench:
	PYTHONPATH=src $(PY) bench/run.py
