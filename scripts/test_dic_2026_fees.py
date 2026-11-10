"""Fee suite: PostgreSQL isolation is enforced by dic_fee_postgres.py; never read .env."""
import ast
from pathlib import Path
import socket
import sys

if 'FEE_DATABASE' not in globals():
    # -I excludes this directory from sys.path, so add only our own script directory.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dic_fee_postgres import main
    raise SystemExit(main())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def no_network(*args, **kwargs):
    raise RuntimeError('Network is disabled for the isolated fee tests.')


socket.socket.connect = no_network
from django.conf import settings

literals = {}
for node in ast.parse((ROOT / 'backend/config/settings/base.py').read_text(encoding='utf-8')).body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in {'INSTALLED_APPS', 'MIDDLEWARE', 'REST_FRAMEWORK', 'AUTH_PASSWORD_VALIDATORS'}:
            literals[node.targets[0].id] = ast.literal_eval(node.value)

settings.configure(**literals,
    SECRET_KEY='synthetic-isolated-fee-tests-only', DEBUG=False,
    DATABASES={'default': FEE_DATABASE},
    ROOT_URLCONF='config.urls', AUTH_USER_MODEL='accounts.User',
    DEFAULT_AUTO_FIELD='django.db.models.BigAutoField', TIME_ZONE='Africa/Lagos', USE_TZ=True,
    ALLOWED_HOSTS=['testserver'], STATIC_URL='/static/',
    TEMPLATES=[dict(BACKEND='django.template.backends.django.DjangoTemplates', APP_DIRS=True,
        OPTIONS={'context_processors': ['django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']})],
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_unit_mock',
    PAYSTACK_CALLBACK_URL='https://example.test/dic/register/payment-return',
    PAYSTACK_HTTP_TIMEOUT_SECONDS=1, DIC_PORTAL_ACCOUNTS_ENABLED=True,
    DIC_PORTAL_EMAIL_VERIFY_URL='https://example.test/dic/participant',
    DIC_MEMORY_STORAGE='disabled', DIC_FEEDBACK_PRIVACY_KEY='synthetic-fee-tests',
)
import django
FEE_INSTALL_GUARDS()
django.setup()
from django.apps import apps
from django.core.management import call_command
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.state import ProjectState
from django.test.runner import DiscoverRunner

loader = MigrationLoader(None)
changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph)
if changes:
    raise RuntimeError('Model/migration drift: ' + str(changes))


class IsolatedRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        if FEE_REUSE:
            FEE_VERIFY_REUSE()
            # Receipt-verified existing schema only: no migrate, flush or reset.
            return None
        # The controller created exactly one empty PostgreSQL database. Never let
        # Django choose, reuse, create, clone or drop a database of its own.
        FEE_VERIFY_EMPTY()
        call_command('migrate', interactive=False, verbosity=1)
        from dic.models import CampEdition
        edition = CampEdition.objects.get(year=2026)
        assert edition.registration_categories.count() == 5
        assert edition.early_bird_cutoff_at is None
        assert edition.registration_status == 'draft' and not edition.is_active
        # Clear only the identity-verified disposable DB for legacy fixtures.
        call_command('flush', interactive=False, verbosity=0)
        return None

    def teardown_databases(self, old_config, **kwargs):
        from django.db import connections
        connections.close_all()
        # Cleanup is a separately approved command using the creation receipt.


labels = sys.argv[1:] or [
    'dic.test_2026_fees',
    'dic.tests.RegistrationApiTests',
    'dic.tests.PaymentApiTests',
    'dic.test_payment_hardening.PaymentEvidenceTests',
    'dic.test_registration_privacy.RegistrationPrivacyPolicyTests',
]
raise SystemExit(bool(IsolatedRunner(verbosity=1, interactive=False).run_tests(labels)))
