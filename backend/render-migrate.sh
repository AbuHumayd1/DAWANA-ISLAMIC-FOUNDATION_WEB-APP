#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
case "${DJANGO_SETTINGS_MODULE:-}" in
  config.settings.staging|config.settings.production|config.settings.render) ;;
  *) echo "Explicit staging/production/Render settings required." >&2; exit 1 ;;
esac
: "${RELEASE_DATABASE_NAME:?An explicit approved release database identity is required}"
: "${RELEASE_DATABASE_HOST:?An explicit approved release database hostname is required}"
: "${RELEASE_DATABASE_PORT:?An explicit approved release database port is required}"
: "${RELEASE_DATABASE_ROLE:?An explicit approved release database role is required}"
: "${RELEASE_DATABASE_CLUSTER_ID:?An independently verified PostgreSQL cluster identity is required}"
# Inspection only. Pending schema stops deployment and prints the exact plan.
# Application is a separate manually approved command, never a build/start hook.
exec python manage.py release_migrations \
  --database-name "$RELEASE_DATABASE_NAME" \
  --hostname "$RELEASE_DATABASE_HOST" \
  --port "$RELEASE_DATABASE_PORT" \
  --role "$RELEASE_DATABASE_ROLE" \
  --cluster-id "$RELEASE_DATABASE_CLUSTER_ID"
