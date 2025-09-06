#!/usr/bin/env bash
set -euo pipefail

# Generate a reproducible lock file from requirements.txt.
# Usage:
#   1) source .venv/bin/activate
#   2) ./generate_lock.sh

if [ -z "${VIRTUAL_ENV-}" ]; then
  echo "⚠️  Please activate your virtualenv first:  source .venv/bin/activate"
  exit 1
fi

python -m pip install --upgrade pip
pip install -r requirements.txt

# Freeze exact versions to a lock file
pip freeze > requirements.lock.txt
echo "✅ Wrote requirements.lock.txt"
