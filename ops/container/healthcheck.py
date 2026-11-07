"""DB-dependent internal readiness. No supplied credentials or response logging."""
import sys
from urllib.request import ProxyHandler, build_opener

try:
    # Provider HTTP_PROXY settings must never redirect this loopback-only probe.
    with build_opener(ProxyHandler({})).open('http://127.0.0.1:9090/_container/ready', timeout=4) as response:
        healthy = response.status == 200 and response.read(128).strip() == b'{"status":"ok"}'
except Exception:
    healthy = False
sys.exit(0 if healthy else 1)
