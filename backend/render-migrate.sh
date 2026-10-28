#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
case "${DJANGO_SETTINGS_MODULE:-}" in
  config.settings.staging|config.settings.production) ;;
  *) echo "Explicit staging/production settings required." >&2; exit 1 ;;
esac
: "${RELEASE_DATABASE_NAME:?An explicit approved release database identity is required}"
# Inspection only. Pending schema stops deployment and prints the exact plan.
# Application is a separate manually approved command, never a build/start hook.
exec python manage.py release_migrations --database-name "$RELEASE_DATABASE_NAME"
