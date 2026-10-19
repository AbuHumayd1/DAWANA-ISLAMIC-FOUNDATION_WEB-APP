#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "${DJANGO_SETTINGS_MODULE:-}" != "config.settings.staging" ]; then
  echo "Render staging build requires config.settings.staging." >&2
  exit 1
fi
python -m pip install -r requirements.txt -c constraints-staging.txt
python manage.py check --deploy --fail-level WARNING
python manage.py collectstatic --noinput
# Migrations are deliberately a separate, approved pre-deploy operation.
