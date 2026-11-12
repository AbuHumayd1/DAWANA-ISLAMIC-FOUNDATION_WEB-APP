"""Database-free policy tests. No dotenv, database setup, migrations or network."""
import ast
import os
from pathlib import Path
import socket
import sys
import unittest

sys.dont_write_bytecode = True
os.environ.pop('DJANGO_SETTINGS_MODULE', None)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def denied(*args, **kwargs):
    raise RuntimeError('Database and network access are forbidden in policy tests.')


socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
from django.conf import settings
from django.db.backends.base.base import BaseDatabaseWrapper
BaseDatabaseWrapper.ensure_connection = denied
literals = {}
for node in ast.parse((ROOT / 'backend/config/settings/base.py').read_text(encoding='utf-8')).body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in {'INSTALLED_APPS', 'MIDDLEWARE', 'REST_FRAMEWORK', 'AUTH_PASSWORD_VALIDATORS'}:
            literals[node.targets[0].id] = ast.literal_eval(node.value)
settings.configure(**literals, SECRET_KEY='synthetic-database-free-production-policy-tests',
    DEBUG=False, DATABASES={'default': {'ENGINE': 'django.db.backends.dummy'}},
    ROOT_URLCONF='config.urls', AUTH_USER_MODEL='accounts.User',
    DEFAULT_AUTO_FIELD='django.db.models.BigAutoField', TIME_ZONE='Africa/Lagos', USE_TZ=True,
    ALLOWED_HOSTS=['testserver'], STATIC_URL='/static/', BASE_DIR=ROOT / 'backend',
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DEFAULT_FROM_EMAIL='sender@example.test',
    PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='sk_test_synthetic', PAYSTACK_LIVE_ENABLED=False,
    PAYSTACK_CALLBACK_URL='https://portal.example.test/dic/register/payment-return', PAYSTACK_HTTP_TIMEOUT_SECONDS=5,
    DIC_PORTAL_ACCOUNTS_ENABLED=True, DIC_PORTAL_EMAIL_VERIFY_URL='https://portal.example.test/dic/participant',
    DIC_MEMORY_STORAGE='disabled', DIC_FEEDBACK_PRIVACY_KEY='synthetic-policy-tests',
    TEMPLATES=[dict(BACKEND='django.template.backends.django.DjangoTemplates',
        DIRS=[ROOT / 'backend' / 'dic' / 'templates'], APP_DIRS=True)])
import django
django.setup()
from django.test import SimpleTestCase, TestCase, TransactionTestCase

labels = sys.argv[1:] or [
    'config.test_render_deployment.RenderDeploymentTests',
    'config.test_public_hosts.PublicHostTests',
    'dic.test_checkout_validation.CheckoutValidationTests',
    'config.test_operations_security.OperationsSecurityTests',
    'dic.test_launch_operations.LaunchOperationsPolicyTests',
    'dic.test_launch_operations.LaunchManagementServiceTests',
    'dic.test_recovery_sprint.FeedbackVersionPolicyTests',
    'dic.test_recovery_sprint.FulfillmentPolicyTests',
    'dic.test_recovery_sprint.RecoveryAuthorizationTests',
    'dic.test_camper_catalogue.CamperCatalogueTests',
    'config.test_native_deployment.NativeDeploymentTests',
    'config.test_request_security.GatewaySecurityTests',
    'dic.test_remediation.RemediationPolicyTests',
    'dic.test_registration_accounts.RegistrationAccountPolicyTests',
    'dic.test_portal_accounts.PortalAccountPolicyTests',
    'dic.test_tutor_registration.TutorPolicyTests',
    'dic.test_production_payments.ProductionPaymentPolicyTests',
    'dic.test_production_payments.PaymentEntitlementModeTests',
    'dic.test_paystack_diagnostics.PaystackDiagnosticTests',
    'dic.test_release_readiness.ReleaseReadinessTests',
    'dic.test_launch_completion.LaunchCompletionPolicyTests',
    'dic.test_storage_production.ProductionStorageTests',
    'dic.test_storage_production.MediaAuthorizationTests',
    'dic.test_render_configuration.RenderConfigurationTests',
    'dic.test_portrait_cutover.PortraitCutoverTests',
    'dic.test_media_corrections.MediaCorrectionTests',
    'dic.test_media_corrections.ShowcaseVisibilityTests',
    'config.test_ci_acceptance.AcceptanceHarnessTests',
]
suite = unittest.defaultTestLoader.loadTestsFromNames(labels)


def validate_suite(node):
    if isinstance(node, unittest.TestSuite):
        for child in node:
            validate_suite(child)
    elif not isinstance(node, SimpleTestCase) or isinstance(node, (TestCase, TransactionTestCase)) or node.databases:
        raise RuntimeError('Only database-free SimpleTestCase tests are permitted: '+node.id())


validate_suite(suite)
if os.environ.get('DAWANA_CI_ACCEPTANCE') == '1':
    from config.ci_acceptance import run_policy_suite
    raise SystemExit(not run_policy_suite(suite))
raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
