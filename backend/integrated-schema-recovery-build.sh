#!/usr/bin/env bash
# ONE TIME ONLY. Intentional failed build preserves the healthy Render runtime.
set +x
set -euo pipefail
umask 077
cd "$(dirname "$0")"
if ! python -B -m config.integrated_schema_recovery; then
  echo '[schema-recovery] STOP: no application promotion; inspect receipt privately.' >&2
  exit 1
fi
echo '[schema-recovery] COMPLETE: deliberately failing build; no application promotion.' >&2
exit 1
