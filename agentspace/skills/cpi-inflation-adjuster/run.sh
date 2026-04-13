#!/usr/bin/env bash
# Run a cpi-inflation-adjuster script using the shared skills venv.
# Usage: bash run.sh adjust.py --amount 100 --from-year 1980 --to-year 2024
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/../.venv"
if [ -f "$VENV/Scripts/python" ]; then
    PYTHON="$VENV/Scripts/python"
elif [ -f "$VENV/bin/python" ]; then
    PYTHON="$VENV/bin/python"
else
    echo "Error: shared venv not found at $VENV" >&2
    exit 1
fi
exec "$PYTHON" "$DIR/scripts/$1" "${@:2}"
