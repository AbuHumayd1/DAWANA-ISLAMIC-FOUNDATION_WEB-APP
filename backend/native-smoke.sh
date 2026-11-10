#!/usr/bin/env bash
# Isolated CI only: synthetic credentials and proxy headers, never production.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -e .env ] || [ -e backend/.env ]; then
  echo 'Synthetic native smoke requires a clean checkout without dotenv files.' >&2
  exit 1
fi
export PUBLIC_HOST=native.example.test
export FRONTEND_ORIGIN=https://frontend.example.test
export DJANGO_SETTINGS_MODULE=config.settings.zevcloud
export DJANGO_SECRET_KEY=ci-only-public-configuration-secret-not-for-production-use-123456
export DATABASE_URL=postgresql://synthetic:synthetic@127.0.0.1:1/synthetic
export DB_CONNECT_TIMEOUT=2
# Prove web startup does not depend on automation or delivery credentials.
unset DIC_AUTOMATION_ACTOR_ID DIC_RECOVERY_ENCRYPTION_KEY DEFAULT_FROM_EMAIL RESEND_API_KEY
export PAYSTACK_MODE=test PAYSTACK_LIVE_ENABLED=false PAYSTACK_SECRET_KEY=''
export PORT=8080
python backend/manage.py check --deploy --fail-level ERROR
# Import/parse the actual worker command without running jobs or touching a DB.
python backend/manage.py run_dic_workers --help > /dev/null
if worker_output=$(bash backend/native-start.sh worker 2>&1); then
  echo 'Worker unexpectedly accepted minimal web configuration.' >&2
  exit 1
fi
printf '%s' "$worker_output" | grep -q 'Explicit application mode and automation actor are required'
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
  if [ "$(probe /api/v1/dic/operations/auth/csrf/ || true)" = 200 ]; then started=true; break; fi
  if ! kill -0 "$web_pid" 2>/dev/null; then
    echo 'Native web process exited before startup completed.' >&2
    if wait "$web_pid"; then exit 1; else exit $?; fi
  fi
  sleep 1
done
[ "$started" = true ]
[ "$(probe /dic/register/payment-return)" = 404 ]
[ "$(probe /dic/participant)" = 404 ]
[ "$(probe /api/v1/not-a-route/)" = 404 ]
[ "$(probe /assets/missing.js)" = 404 ]
# A working API/CSRF endpoint must not make unavailable DB/worker readiness pass.
[ "$(probe /api/v1/health/)" = 503 ]
[ "$(probe /api/v1/health/web/)" = 503 ]
[ "$(curl --silent --output /dev/null --write-out '%{http_code}' -H 'Host: native.example.test' http://127.0.0.1:8080/)" = 400 ]
# Exercise real cross-origin CSRF bootstrap/preflight without database access.
headers=$(curl --silent --fail --dump-header - --output /dev/null --max-time 10 \
  -H 'Host: native.example.test' -H 'X-Forwarded-Proto: https' \
  -H 'Origin: https://frontend.example.test' http://127.0.0.1:8080/api/v1/dic/participant/auth/csrf/)
printf '%s' "$headers" | grep -qi '^Access-Control-Allow-Origin: https://frontend.example.test'
printf '%s' "$headers" | grep -qi '^Access-Control-Allow-Credentials: true'
headers=$(curl --silent --fail --dump-header - --output /dev/null --max-time 10 -X OPTIONS \
  -H 'Host: native.example.test' -H 'X-Forwarded-Proto: https' \
  -H 'Origin: https://frontend.example.test' -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrftoken' \
  http://127.0.0.1:8080/api/v1/dic/operations/auth/login/)
printf '%s' "$headers" | grep -qi '^Access-Control-Allow-Origin: https://frontend.example.test'
headers=$(curl --silent --fail --dump-header - --output /dev/null --max-time 10 \
  -H 'Host: native.example.test' -H 'X-Forwarded-Proto: https' \
  -H 'Origin: https://attacker.example.test' http://127.0.0.1:8080/api/v1/dic/participant/auth/csrf/)
if printf '%s' "$headers" | grep -qi '^Access-Control-Allow-Origin:'; then exit 1; fi
echo 'PASS: standalone API routing, CORS/CSRF bootstrap, scheme rejection and unavailable readiness.'
