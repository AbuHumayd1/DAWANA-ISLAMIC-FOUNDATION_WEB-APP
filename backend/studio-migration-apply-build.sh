#!/usr/bin/env bash
# Explicit owner approval required. This build always fails to preserve the
# previously running production app, even if schema application succeeds.
set +x
set -euo pipefail
umask 077
cd "$(dirname "$0")"
if ! python -B -m config.studio_migration_apply; then
  echo '[studio-migration] STOP: application not confirmed; old runtime retained.' >&2
  exit 1
fi
echo '[studio-migration] SCHEMA APPLIED; deliberately failing build; old runtime retained.'
exit 1
