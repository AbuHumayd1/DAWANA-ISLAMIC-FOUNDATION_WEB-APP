"""Supervisor event protocol; any application child exit fails the container."""
import os
from pathlib import Path
import signal
import sys

while True:
    sys.stdout.write('READY\n')
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        break
    headers = dict(part.split(':', 1) for part in line.split())
    payload = sys.stdin.read(int(headers['len']))
    sys.stdout.write('RESULT 2\nOK')
    sys.stdout.flush()
    if any('processname:' + name + ' ' in payload for name in ('gunicorn', 'nginx', 'workers')):
        Path('/run/dawana/child-failed').touch()
        os.kill(os.getppid(), signal.SIGTERM)
