#!/usr/bin/env bash
# LOCAL/CI SYNTHETIC ONLY. Creates disposable containers/certificates; never a DB.
set -Eeuo pipefail
image=${1:?Supply the locally built image tag}
name="dawana-package-smoke-$$"
evidence=$(mktemp -d)
# Report failures before cleanup; never dump the container environment or TLS keys.
smoke_error() {
  printf 'ERROR: %s:%s: exit %s: %s\n' "${BASH_SOURCE[1]}" "$2" "$1" "$3" >&2
}
cleanup() {
  status=$?
  trap - ERR
  set +e
  if test "$status" -ne 0; then
    echo "ERROR: synthetic smoke failed; container state and last 200 log lines follow." >&2
    docker inspect --format '{{json .State}}' "$name" >&2
    docker logs --tail 200 "$name" >&2
  fi
  docker rm -f "$name" >/dev/null 2>&1
  exit "$status"
}
trap 'smoke_error "$?" "$LINENO" "$BASH_COMMAND"' ERR
trap cleanup EXIT
# Synthetic short-lived TLS fixture, never a production certificate/key.
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -keyout "$evidence/key.pem" -out "$evidence/cert.pem" \
  -subj '/CN=foundation.example.test' -addext 'subjectAltName=DNS:foundation.example.test' >/dev/null 2>&1
chmod 644 "$evidence/key.pem" # Disposable fixture must be readable by UID 10001.
chmod 755 "$evidence" # UID 10001 must also be able to traverse the bind mount.
docker run -d --name "$name" --read-only --tmpfs /run/dawana:uid=10001,gid=10001,mode=700 --tmpfs /tmp:mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1::8080 -v "$evidence:/run/tls:ro" \
  -e PUBLIC_HOST=foundation.example.test -e GATEWAY_TLS_MODE=direct -e DAWANA_WEBSITE_ONLY=false -e DIC_BACKGROUND_WORKER_ENABLED=false \
  -e GATEWAY_TLS_CERT_FILE=/run/tls/cert.pem -e GATEWAY_TLS_KEY_FILE=/run/tls/key.pem \
  -e DAWANA_TRUSTED_GATEWAYS=127.0.0.1/32 -e DJANGO_TRUST_PROXY_HTTPS=true \
  -e DJANGO_ALLOWED_HOSTS=foundation.example.test \
  -e DJANGO_CSRF_TRUSTED_ORIGINS=https://foundation.example.test \
  -e DJANGO_SECRET_KEY=synthetic-container-smoke-only-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  -e DB_NAME=synthetic_unreachable -e DB_USER=synthetic -e DB_HOST=127.0.0.1 -e DB_PORT=1 \
  -e DB_SSLMODE=verify-full -e PAYSTACK_MODE=test -e PAYSTACK_LIVE_ENABLED=false \
  -e DIC_MEMORY_STORAGE=disabled "$image" >/dev/null
port=$(docker port "$name" 8080/tcp | awk -F: '{print $NF}')
request() { curl --silent --show-error --noproxy '*' --cacert "$evidence/cert.pem" \
  --resolve "foundation.example.test:$port:127.0.0.1" "$@"; }
base="https://foundation.example.test:$port"
# Nginx liveness/SPA responses do not prove Gunicorn has loaded Django.
# Use a database-free Django response before checking routing. Do not wait for
# readiness=200: the synthetic database is deliberately unreachable.
backend_status=000
for attempt in $(seq 1 30); do
  backend_status=$(request --connect-timeout 1 --max-time 2 -o /dev/null -w '%{http_code}' \
    "$base/api/v1/not-a-route/" 2>/dev/null) || backend_status=000
  case "$backend_status" in
    404) break ;;
    000|502) ;; # Transport/upstream startup only; other statuses are real failures.
    *) echo "ERROR: Django startup probe expected 404, got $backend_status." >&2; exit 1 ;;
  esac
  if test "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null)" != true; then
    echo "ERROR: direct-TLS container exited before Django responded." >&2
    exit 1
  fi
  sleep 1
done
if test "$backend_status" != 404; then
  echo "ERROR: Django did not respond with 404 within 30 attempts (last status $backend_status)." >&2
  exit 1
fi
test "$(request "$base/_container/live")" = gateway-alive
test "$(request -o /dev/null -w '%{http_code}' "$base/dic/register/payment-return")" = 200
test "$(request -o /dev/null -w '%{http_code}' "$base/media/forbidden.jpg")" = 404
test "$(request -o /dev/null -w '%{http_code}' "$base/assets/missing.js")" = 404
test "$(request -o /dev/null -w '%{http_code}' "$base/api/v1/not-a-route/")" = 404
test "$(request -o /dev/null -w '%{http_code}' "$base/static/admin/css/base.css")" = 200
test "$(request -o /dev/null -w '%{http_code}' "$base/_container/ready")" = 503
test "$(request -o /dev/null -w '%{http_code}' -H 'X-Forwarded-Proto: http' -H 'X-Dawana-Client-IP: spoof' "$base/api/v1/health/")" = 503
request -D "$evidence/headers" "$base/api/v1/health/" > /dev/null
grep -qi 'cache-control:.*no-store' "$evidence/headers"
docker kill --signal TERM "$name" >/dev/null
test "$(timeout 60s docker wait "$name")" = 0
echo 'PASS: synthetic direct-TLS routing, static, DB-unavailable readiness and shutdown.'
echo "Synthetic evidence retained at $evidence (contains disposable TLS fixtures)."
