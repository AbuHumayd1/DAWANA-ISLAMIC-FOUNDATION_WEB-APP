#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Build without production settings, credentials, connections or migrations.
cd backend
python -m config.runtime_requirements
DJANGO_SETTINGS_MODULE=config.settings.build python manage.py collectstatic --noinput
# A failed candidate build leaves the current healthy Render deployment running.
# This plans/inspects only. Never apply migrations from an ordinary build/start.
if [[ "${RENDER:-}" == 'true' ]]; then
  python -B -m config.deployment_schema_guard
fi
