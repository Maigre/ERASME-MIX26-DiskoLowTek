#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "No .venv found — run ./install.sh first."
    exit 1
fi

exec .venv/bin/python src/server.py "$@"
