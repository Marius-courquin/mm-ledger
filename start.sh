#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# 1. Venv
if [ ! -d .venv ]; then
    echo ">> Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

# 2. Deps
echo ">> Installing dependencies..."
pip install -q -e ".[dev]" 2>&1 | tail -1

# 3. Reset vault if requested
if [ "$1" = "--reset" ]; then
    echo ">> Resetting vault and database..."
    rm -f data/vault.db data/ledger.db
fi

# 4. Start
echo ">> Starting mm-ledger on http://localhost:8000"
echo ">> Swagger UI: http://localhost:8000/docs"
exec uvicorn src.main:app --reload --port 8000
