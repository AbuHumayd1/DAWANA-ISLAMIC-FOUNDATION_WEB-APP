#!/usr/bin/env bash
# NEVER promotes a candidate build. Current healthy runtime remains active.
# Pin and verify the fresh PR74 backup checksum before invoking this file.
set +x
set -euo pipefail
umask 077
cd "$(dirname "$0")"
if ! python -B -m config.studio_0047_migration; then
  echo '[media-0047] STOP: schema not confirmed; original runtime retained.' >&2
  exit 1
fi
echo '[media-0047] APPLY VERIFIED; deliberately failing build to prevent promotion.'
exit 1
