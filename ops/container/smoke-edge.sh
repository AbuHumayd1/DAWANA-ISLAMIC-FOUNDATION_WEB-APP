#!/usr/bin/env bash
# Isolated synthetic peer/header and child-failure test; no DB or external calls.
set -Eeuo pipefail
image=${1:?Supply local image tag}
name="dawana-edge-smoke-$$"
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
docker run -d --name "$name" --read-only --tmpfs /run/dawana:uid=10001,gid=10001,mode=700 --tmpfs /tmp:mode=1777 \
  --cap-drop ALL --security-opt no-new-privileges \
  -e PUBLIC_HOST=foundation.example.test -e GATEWAY_TLS_MODE=trusted-edge -e DAWANA_WEBSITE_ONLY=false -e DIC_BACKGROUND_WORKER_ENABLED=false \
  -e EDGE_TRUST_VERIFIED=1 -e TRUSTED_EDGE_CIDRS=127.0.0.1/32 \
  -e DAWANA_TRUSTED_GATEWAYS=127.0.0.1/32 -e DJANGO_TRUST_PROXY_HTTPS=true \
  -e DJANGO_ALLOWED_HOSTS=foundation.example.test \
  -e DJANGO_CSRF_TRUSTED_ORIGINS=https://foundation.example.test \
  -e DJANGO_SECRET_KEY=synthetic-container-smoke-only-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  -e DB_NAME=synthetic_unreachable -e DB_USER=synthetic -e DB_HOST=127.0.0.1 -e DB_PORT=1 \
  -e DB_SSLMODE=verify-full -e PAYSTACK_MODE=test -e PAYSTACK_LIVE_ENABLED=false \
  -e DIC_MEMORY_STORAGE=disabled "$image" >/dev/null
ready=0
for attempt in $(seq 1 30); do
  if docker exec "$name" python -c 'import socket; s=socket.create_connection(("127.0.0.1", 8080), timeout=1); s.close()' >/dev/null 2>&1; then
    ready=1
    break
  fi
  if test "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null)" != true; then
    echo "ERROR: trusted-edge container exited before readiness." >&2
    docker logs "$name" >&2
    exit 1
  fi
  sleep 1
done
if test "$ready" != 1; then
  echo "ERROR: trusted-edge gateway did not listen on port 8080 within 30 attempts." >&2
  docker logs "$name" >&2
  exit 1
fi
docker exec -i "$name" python - <<'PY'
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from time import sleep
def status(path, headers):
    request = Request('http://127.0.0.1:8080' + path, headers={'Host': 'foundation.example.test', **headers})
    try:
        with urlopen(request, timeout=5) as response: return response.status
    except HTTPError as error: return error.code
assert status('/', {}) == 400
assert status('/', {'X-Forwarded-Proto': 'http', 'X-Real-IP': '192.0.2.4'}) == 400
trusted = {'X-Forwarded-Proto': 'https', 'X-Real-IP': '192.0.2.4'}
# A listening gateway can still return 502 while Gunicorn loads Django.
# Wait for a database-free application response, not DB-dependent readiness.
for attempt in range(30):
    try:
        actual = status('/api/v1/not-a-route/', trusted)
    except (URLError, TimeoutError, ConnectionError):
        actual = None
    if actual == 404:
        break
    assert actual in (None, 502), f'Django startup probe expected 404, got {actual}'
    sleep(1)
else:
    raise AssertionError(f'Django did not respond with 404 within 30 attempts (last status {actual})')
actual = status('/dic/register/payment-return', trusted)
print(f'Trusted-edge payment-return: expected 200, got {actual}', flush=True)
assert actual == 200, f'Expected 200, got {actual}'
assert status('/api/v1/health/', {**trusted, 'X-Forwarded-For': 'spoof', 'X-Dawana-Client-IP': 'spoof'}) == 503
assert status('/api/v1/health/', {**trusted, 'X-Real-IP': 'not-an-ip'}) == 400
print('PASS: synthetic edge scheme/header boundary; database remains unavailable.')
PY
docker exec "$name" python -c 'import os, signal; from pathlib import Path; os.kill(int(Path("/run/dawana/gunicorn.pid").read_text()), signal.SIGKILL)'
test "$(timeout 60s docker wait "$name")" = 1
echo 'PASS: child failure propagated to nonzero container exit.'
