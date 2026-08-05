#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> ruff check"
ruff check src tests examples

echo "==> ruff format --check"
ruff format --check src tests examples

echo "==> mypy"
mypy

echo "==> pytest"
pytest --cov=ledger --cov-report=term-missing

echo "==> worked example"
python3 examples/worked_example.py

echo "==> daily job (offline)"
python3 examples/daily_job.py

echo "==> agent demo (offline path; skips live agent without OPENAI_API_KEY)"
python3 examples/agent_demo.py

echo "All checks passed."
