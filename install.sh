#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# ---- Install uv if missing ----
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "uv $(uv --version)"

# ---- Create venv & install deps ----
uv venv .venv --python 3.13
uv pip install -r requirements.txt

echo ""
echo "Done. Run the app with:  ./run.sh"
