"""Fixed loopback-only disposable workspace cluster. Never uses DB env values."""
from .phase_a_test import *  # noqa: F403
TEST_RUNNER = 'config.phase_a_runner.PhaseARunner'
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'HOST': '127.0.0.1',
    'PORT': '55483', 'NAME': 'postgres', 'USER': 'phase_a_synthetic', 'PASSWORD': '',
    'OPTIONS': {'connect_timeout': 3, 'sslmode': 'disable'},
    'TEST': {'NAME': 'test_dic_core_20261112190000_50484153', 'TEMPLATE': 'template0'}}}
