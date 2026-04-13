#!/usr/bin/env bash
# Run a historical-fx script using the shared skills venv.
# Usage: bash run.sh convert.py --amount 1000 --from USD --to JPY --date 2020-03-15
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
