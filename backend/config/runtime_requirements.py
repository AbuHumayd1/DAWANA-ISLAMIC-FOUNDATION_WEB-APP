"""Offline build gate; no Django setup, secrets, database or network access."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from importlib.metadata import version


def verify_runtime():
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError('Production requires the CI-tested Python 3.13 runtime.')
    if version('Django') != '5.2.18':
        raise RuntimeError('Production Django must match the tested pinned version.')
    for package in ('gunicorn', 'reportlab', 'Pillow', 'qrcode', 'psycopg'):
        version(package)
    for name in ('LiberationSans-Regular.ttf', 'LiberationSans-Bold.ttf', 'LiberationSerif-Bold.ttf'):
        if not any((Path(root) / name).is_file() for root in (
                '/usr/share/fonts/truetype/liberation2', '/usr/share/fonts/truetype/liberation')):
            raise RuntimeError('Install the approved Liberation font package before building.')
    binary = os.environ.get('DIC_FFPROBE_BINARY') or shutil.which('ffprobe')
    if not binary:
        candidate = Path(__file__).resolve().parents[1] / '.runtime/ffprobe'
        binary = str(candidate) if candidate.is_file() else None
    if not binary:
        raise RuntimeError('ffprobe is required; media validation must not be skipped.')
    subprocess.run([binary, '-version'], check=True, timeout=10, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    verify_runtime()
    print('PASS: offline Python, PDF/font and ffprobe runtime requirements.')
