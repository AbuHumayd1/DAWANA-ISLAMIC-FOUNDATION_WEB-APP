#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "${DJANGO_SETTINGS_MODULE:-}" != "config.settings.staging" ]; then
  echo "Render staging start requires config.settings.staging." >&2
  exit 1
fi
exec python -m gunicorn config.wsgi:application --config gunicorn.conf.py
