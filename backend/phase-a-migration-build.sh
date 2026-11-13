#!/usr/bin/env bash
# ONE TIME ONLY. A failed Render build is intentional, even after SQL succeeds.
set +x
set -euo pipefail
umask 077
cd "$(dirname "$0")"
if ! python -B -m config.phase_a_migration_build; then
  echo '[phase-a-migration] STOP: migration build blocked; no backend promotion.' >&2
  exit 1
fi
echo '[phase-a-migration] COMPLETE: database step finished; deliberately failing build to prevent backend promotion.' >&2
exit 1
