"""Local dependency adapter and network-denied disposable SQLite test runner."""
import ctypes.util
import os
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'backend/.venv/Lib/site-packages'
sys.path.extend([str(ROOT / 'backend'), str(SITE)])
LIBS = SITE / 'psycopg_binary.libs'
if sys.platform == 'win32' and LIBS.exists():
    handle = os.add_dll_directory(str(LIBS))
    pq = next(LIBS.glob('libpq-*.dll'))
    original_find = ctypes.util.find_library
    ctypes.util.find_library = lambda name: str(pq) if name in ('pq', 'libpq.dll') else original_find(name)
    os.environ['PSYCOPG_IMPL'] = 'python'
os.environ['DJANGO_SETTINGS_MODULE'] = next((name for name in (
    'config.settings.phase_a_postgres', 'config.settings.phase_a_tutor')
    if '--settings=' + name in sys.argv), 'config.settings.phase_a_test')

original_connect = socket.socket.connect
def deny_network(sock, address):
    if os.environ['DJANGO_SETTINGS_MODULE'] in ('config.settings.phase_a_postgres', 'config.settings.phase_a_tutor') and address == ('127.0.0.1', 55483):
        return original_connect(sock, address)
    raise RuntimeError('Network is disabled in Phase A synthetic tests.')

socket.socket.connect = deny_network
socket.create_connection = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('External network disabled.'))
import django
django.setup()
from django.core.management import execute_from_command_line
execute_from_command_line([sys.argv[0], *sys.argv[1:]])
