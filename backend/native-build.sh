#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Build without production settings, credentials, connections or migrations.
cd backend
python -m config.runtime_requirements
DJANGO_SETTINGS_MODULE=config.settings.build python manage.py collectstatic --noinput
