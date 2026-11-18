#!/usr/bin/env bash
# One-time Render build-stage read-only inspection. Intentional failure prevents
# promoting a partially migrated runtime; keep normal Start Command unchanged.
set +x
set -euo pipefail
umask 077
cd "$(dirname "$0")"
if ! python -B -m config.studio_migration_inspect; then
  echo '[studio-migration] STOP: inspection failed; production runtime not promoted.' >&2
  exit 1
fi
echo '[studio-migration] COMPLETE: read-only plan recorded; intentionally failing build; no promotion.'
exit 1
