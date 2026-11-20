#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Approved one-time 0047 release uses the established non-promoting Render build path.
# Never run automatically or during an ordinary deployment.
if [[ "${DAWANA_0047_APPROVAL:-}" == 'APPROVE-DAWANA-MEDIA-0047' ]]; then
  bash backend/media-0047-migration-apply-build.sh
  exit 1
fi
# Build without production settings, credentials, connections or migrations.
cd backend
python -m config.runtime_requirements
DJANGO_SETTINGS_MODULE=config.settings.build python manage.py collectstatic --noinput
# A failed candidate build leaves the current healthy Render deployment running.
# This plans/inspects only. Never apply migrations from an ordinary build/start.
if [[ "${RENDER:-}" == 'true' ]]; then
  python -B -m config.deployment_schema_guard
fi
