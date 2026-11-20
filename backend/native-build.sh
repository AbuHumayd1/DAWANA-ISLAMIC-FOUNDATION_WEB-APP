#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Build without production settings, credentials, connections or migrations.
cd backend
# Deliberately failed, owner-gated one-time schema application. This NEVER
# promotes the candidate; it preserves the currently live web service.
if [[ "${DAWANA_AFTERCAMP_0046_APPROVAL:-}" == 'APPROVE-DAWANA-AFTERCAMP-0046' ]]; then
  if ! python -B -m config.aftercamp_0046_apply; then
    echo '[aftercamp-0046] STOP: schema application not confirmed; old runtime retained.' >&2
    exit 1
  fi
  echo '[aftercamp-0046] Schema applied; deliberately failing build; old runtime retained.' >&2
  exit 1
fi
python -m config.runtime_requirements
DJANGO_SETTINGS_MODULE=config.settings.build python manage.py collectstatic --noinput
# A failed candidate build leaves the current healthy Render deployment running.
# This plans/inspects only. Never apply migrations from an ordinary build/start.
if [[ "${RENDER:-}" == 'true' ]]; then
  python -B -m config.deployment_schema_guard
fi
