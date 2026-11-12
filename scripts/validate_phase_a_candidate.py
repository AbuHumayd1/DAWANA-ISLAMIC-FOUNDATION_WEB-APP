"""Execute candidate tests with installed local dependencies, not mixed source.

On Windows the existing workspace dependency store can be junctioned at
backend/.venv. This adapter supplies those dependencies to isolated startup
subprocesses without weakening their database/network denial guards.
"""
import ctypes.util
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT/'backend/.venv/Lib/site-packages'
LIBS = SITE/'psycopg_binary.libs'
prefix = 'import sys\n' + f'sys.path.append({str(SITE)!r})\n'
if sys.platform == 'win32' and LIBS.exists():
    pq = next(LIBS.glob('libpq-*.dll'))
    prefix += ('import os, ctypes.util\n'
        'os.environ["PSYCOPG_IMPL"]="python"\n'
        f'_rc_dll = os.add_dll_directory({str(LIBS)!r})\n'
        '_rc_find=ctypes.util.find_library\n'
        f'ctypes.util.find_library=lambda name: {str(pq)!r} if name in ("pq","libpq.dll") else _rc_find(name)\n')
original_run = subprocess.run


def local_dependencies(args, *positional, **kwargs):
    if isinstance(args, list) and args[:4] == [sys.executable, '-I', '-B', '-c']:
        args = [*args[:4], prefix + args[4], *args[5:]]
    return original_run(args, *positional, **kwargs)


subprocess.run = local_dependencies
os.chdir(ROOT)
sys.argv = [str(ROOT/'scripts/run_phase_a_tests.py'), *sys.argv[1:]]
runpy.run_path(sys.argv[0], run_name='__main__')
