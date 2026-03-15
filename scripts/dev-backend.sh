#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR/backend"

PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "backend/.venv is missing. Run ./scripts/bootstrap-backend.sh first." >&2
  exit 1
fi

echo "Starting backend with $PYTHON_BIN"
"$PYTHON_BIN" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
