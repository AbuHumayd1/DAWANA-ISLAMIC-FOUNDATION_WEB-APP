#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "${RENDER:-}" == 'true' ]]; then
  export DJANGO_SETTINGS_MODULE=config.settings.render
else
  export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.zevcloud}"
fi
case "${1:-web}" in
  # The build validates multimedia tools. Web startup must reach Gunicorn
  # without probing ffprobe, fonts or other media-only dependencies again.
  web)
    echo '[startup] Launching Gunicorn web process.' >&2
    exec python -m gunicorn config.wsgi:application --config gunicorn.native.py
    ;;
  worker)
    python -m config.runtime_requirements
    exec python manage.py run_dic_workers --health-port "${PORT:-8080}"
    ;;
  *) echo 'Use native-start.sh web or native-start.sh worker.' >&2; exit 1 ;;
esac
