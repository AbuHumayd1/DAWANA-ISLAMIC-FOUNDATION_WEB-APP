#!/usr/bin/env bash
# Only invoked by the temporary, explicitly approved Render build gate.
# The candidate build must NOT be promoted, even after successful migration.
set +x
set -euo pipefail
umask 077
cd "$(dirname "$0")"
if ! python -B -m config.studio_0048_migration; then
  echo '[carousel-0048] STOP: migration unverified; production runtime retained.' >&2
  exit 1
fi
echo '[carousel-0048] APPLICATION VERIFIED: intentionally failing build; runtime retained.'
exit 1
