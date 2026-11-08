#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install -r backend/requirements.txt -c backend/constraints-staging.txt
python -m pip check
npm --prefix dawana-platform ci --include=dev
