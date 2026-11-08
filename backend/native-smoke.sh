#!/usr/bin/env bash
# Isolated CI only: synthetic credentials and proxy headers, never production.
set -euo pipefail
cd "$(dirname "$0")/.."
export PUBLIC_HOST=native.example.test
export DJANGO_SECRET_KEY=ci-only-public-configuration-secret-not-for-production-use-123456
export DATABASE_URL=postgresql://synthetic:synthetic@127.0.0.1:1/synthetic
export DB_CONNECT_TIMEOUT=2
export ZEV_PROXY_HEADERS_VERIFIED=true
export DIC_AUTOMATION_ACTOR_ID=1
export DIC_RECOVERY_ENCRYPTION_KEY
DIC_RECOVERY_ENCRYPTION_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
export DEFAULT_FROM_EMAIL=ci@example.test RESEND_API_KEY=synthetic-ci-only
export PAYSTACK_MODE=test PAYSTACK_LIVE_ENABLED=false PAYSTACK_SECRET_KEY=''
export PORT=8080
bash backend/native-start.sh web &
web_pid=$!
cleanup() {
  status=$?
  trap - EXIT
  kill -TERM "$web_pid" 2>/dev/null || true
  wait "$web_pid" 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT
probe() {
  curl --silent --output /dev/null --write-out '%{http_code}' --max-time 10 \
    -H 'Host: native.example.test' -H 'X-Forwarded-Proto: https' "http://127.0.0.1:8080$1"
}
started=false
for attempt in $(seq 1 60); do
  if [ "$(probe / || true)" = 200 ]; then started=true; break; fi
  if ! kill -0 "$web_pid" 2>/dev/null; then
    echo 'Native web process exited before startup completed.' >&2
    if wait "$web_pid"; then exit 1; else exit $?; fi
  fi
  sleep 1
done
[ "$started" = true ]
[ "$(probe /dic/register/payment-return)" = 200 ]
[ "$(probe /dic/participant)" = 200 ]
[ "$(probe /api/v1/not-a-route/)" = 404 ]
[ "$(probe /assets/missing.js)" = 404 ]
# A working homepage must never make unavailable DB/worker readiness pass.
[ "$(probe /api/v1/health/)" = 503 ]
[ "$(curl --silent --output /dev/null --write-out '%{http_code}' -H 'Host: native.example.test' http://127.0.0.1:8080/)" = 400 ]
echo 'PASS: native SPA/API routing, missing assets, scheme rejection and unavailable readiness.'
