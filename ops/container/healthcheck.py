"""DB-dependent internal readiness. No supplied credentials or response logging."""
import sys
from urllib.request import ProxyHandler, build_opener
from urllib.error import HTTPError

try:
    # Provider HTTP_PROXY settings must never redirect this loopback-only probe.
    with build_opener(ProxyHandler({})).open('http://127.0.0.1:9090/_container/ready', timeout=4) as response:
        healthy = response.status == 200 and response.read(128).strip() == b'{"status":"ok"}'
        if not healthy:
            print('Readiness failed [HC_RESPONSE]: expected the exact database-readiness response, not a homepage.', file=sys.stderr)
except HTTPError:
    print('Readiness failed [HC_HTTP]: Django is not ready; check PostgreSQL TLS/connectivity and any enabled worker.', file=sys.stderr)
    healthy = False
except Exception:
    print('Readiness failed [HC_CONNECTION]: private gateway unavailable or timed out; check startup diagnostics.', file=sys.stderr)
    healthy = False
sys.exit(0 if healthy else 1)
