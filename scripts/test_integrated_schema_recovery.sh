#!/usr/bin/env bash
# Synthetic shell entrypoint contracts; never connects to any database.
set -euo pipefail
cd "$(dirname "$0")/.."
bash -n backend/integrated-schema-recovery-build.sh backend/native-build.sh
stub=$(mktemp -d)
printf '#!/bin/sh\nexit 0\n' > "$stub/python"
chmod +x "$stub/python"
if PATH="$stub:$PATH" bash backend/integrated-schema-recovery-build.sh; then
  echo 'ERROR: recovery allowed promotion'; exit 1
fi
printf '#!/bin/sh\nexit 1\n' > "$stub/python"
if PATH="$stub:$PATH" bash backend/integrated-schema-recovery-build.sh; then
  echo 'ERROR: failed recovery allowed promotion'; exit 1
fi
printf '#!/bin/sh\ncase "$*" in *deployment_schema_guard*) exit 1;; *) exit 0;; esac\n' > "$stub/python"
if RENDER=true PATH="$stub:$PATH" bash backend/native-build.sh; then
  echo 'ERROR: unknown schema allowed Render build'; exit 1
fi
RENDER=false PATH="$stub:$PATH" bash backend/native-build.sh
printf '#!/bin/sh\nexit 0\n' > "$stub/python"
RENDER=true PATH="$stub:$PATH" bash backend/native-build.sh
echo 'PASS: five shell barriers and syntax; no database connections.'
