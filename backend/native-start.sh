#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export DJANGO_SETTINGS_MODULE=config.settings.zevcloud
python -m config.runtime_requirements
case "${1:-web}" in
  web) exec python -m gunicorn config.wsgi:application --config gunicorn.native.py ;;
  worker) exec python manage.py run_dic_workers --health-port "${PORT:-8080}" ;;
  *) echo 'Use native-start.sh web or native-start.sh worker.' >&2; exit 1 ;;
esac
