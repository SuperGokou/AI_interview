#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
if [ ! -x .venv/bin/python ] || [ ! -f frontend/dist/index.html ]; then
  echo 'Missing local dependencies/build. See README.md.' >&2
  exit 1
fi
cd backend
exec ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8010}"
