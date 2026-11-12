"""Tutor partition on the same synthetic-only disposable cluster."""
from .phase_a_postgres import *  # noqa: F403
DATABASES['default']['TEST']['NAME'] = 'test_dic_tutor_20261112190000_50484153'  # noqa: F405
