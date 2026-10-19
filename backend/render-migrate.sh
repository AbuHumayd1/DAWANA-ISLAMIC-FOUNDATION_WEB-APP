#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "${DJANGO_SETTINGS_MODULE:-}" != "config.settings.staging" ]; then
  echo "Staging migrations require config.settings.staging." >&2
  exit 1
fi
python manage.py migrate --noinput
python manage.py createcachetable
python manage.py migrate --check
