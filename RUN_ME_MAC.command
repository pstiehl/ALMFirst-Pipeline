#!/bin/bash
# ALM First SE Pipeline — Mac launcher. Double-click in Finder.
set -e
cd "$(dirname "$0")"
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then echo "Install Python 3.11+ from https://www.python.org/downloads/ then double-click again."; read -r; exit 1; fi
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/python -m pip install -q --upgrade pip
./.venv/bin/python -m pip install -q -r requirements.txt
[ -f data/processed/credit_unions.csv.gz ] || ./.venv/bin/python scripts/build_data.py
echo "Opening http://localhost:8501 ... (close this window to stop)"
./.venv/bin/python -m streamlit run app.py
