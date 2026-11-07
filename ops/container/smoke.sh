#!/usr/bin/env bash
# LOCAL/CI SYNTHETIC ONLY. Creates disposable containers/certificates; never a DB.
set -euo pipefail
image=${1:?Supply the locally built image tag}
name="dawana-package-smoke-$$"
evidence=$(mktemp -d)
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
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
  -e PUBLIC_HOST=foundation.example.test -e GATEWAY_TLS_MODE=direct \
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
for attempt in $(seq 1 30); do
  if request "$base/_container/live" > /dev/null 2>&1; then break; fi
  sleep 1
done
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
