#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"

echo "OK: environment ready"
echo "Try:"
echo "  source .venv/bin/activate"
echo "  pytest"
echo "  otranscribe doctor"