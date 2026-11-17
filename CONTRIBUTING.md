# Contributing

Useful contributions:

- An identifier or message field that survives a hop the linker treats as a break, with the primary source (network rules, a usage guideline, an implementation guide).
- Taint accounting rules used by courts or regulators that are not here yet, with the citation.

Code changes:

- `ruff check .`, `ruff format --check .`, `python scripts/check.py`, `mypy` and `pytest -q` must pass.
- Keep identifier links and inferred links apart. An inferred link must never reach the confidence of an identifier link.
- Anything in the simulator that goes beyond what networks do today belongs behind a scenario setting and must be described as hypothetical.
- Synthetic data only. Never commit a real customer, account, address or case.
