#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "${DJANGO_SETTINGS_MODULE:-}" != "config.settings.production" ]; then
  echo "Explicit config.settings.production is required." >&2
  exit 1
fi
python -m pip install -r requirements.txt -c constraints-staging.txt
if [ "${DIC_INSTALL_FFPROBE:-0}" = '1' ]; then
  bash install-ffprobe.sh
fi
python -m config.runtime_requirements
python manage.py check --deploy --fail-level ERROR
python manage.py collectstatic --noinput
# Never migrate or seed during builds. The existing constraint filename is historical.
