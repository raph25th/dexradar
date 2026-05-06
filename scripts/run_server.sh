#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -f ".venv/bin/activate" ]]; then
  echo "Virtual environment was not found at .venv/bin/activate" >&2
  exit 1
fi

source ".venv/bin/activate"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
