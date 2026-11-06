#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "${DJANGO_SETTINGS_MODULE:-}" != "config.settings.production" ]; then
  echo "Explicit config.settings.production is required." >&2
  exit 1
fi
# No schema changes, cache creation, seeding or registration activation on startup.
if [ -z "${DIC_FFPROBE_BINARY:-}" ] && [ -x "$PWD/.runtime/ffprobe" ]; then
  export DIC_FFPROBE_BINARY="$PWD/.runtime/ffprobe"
fi
exec python -m gunicorn config.wsgi:application --config gunicorn.conf.py
