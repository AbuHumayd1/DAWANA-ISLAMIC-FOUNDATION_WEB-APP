import hashlib
import hmac
import json
import uuid
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings
from django.urls import path
from rest_framework.test import APIClient, APITestCase

from . import tests as existing
from .models import PaymentAttempt, RegistrationOrder
from config.urls import urlpatterns as base_patterns
from config.staging_tester_views import TesterLoginView, TesterLogoutView

urlpatterns = [*base_patterns,
    path("api/v1/dic/tester-access/login/", TesterLoginView.as_view(), name="staging-tester-login"),
    path("api/v1/dic/tester-access/logout/", TesterLogoutView.as_view(), name="staging-tester-logout"),
]


@override_settings(
    MIDDLEWARE=[*settings.MIDDLEWARE, "config.staging_tester_access.DICStagingTesterMiddleware"],
    STAGING_DIC_TESTER_RESTRICTION_ENABLED=True,
    STAGING_DIC_TESTER_USERNAMES=["DIF", *[f"dic-tester-{i:02d}" for i in range(1, 10)]],
    ROOT_URLCONF=__name__,
    REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "dic_staging_tester_login": "60/hour",
    }},
    PAYSTACK_MODE="test", PAYSTACK_SECRET_KEY="sk_test_unit_mock",
    ALLOWED_HOSTS=["testserver", "backend-staging.onrender.com"],
)
class StagingTesterAccessTests(APITestCase):
    create_pending_attempt = existing.PaymentApiTests.create_pending_attempt
    provider_result = existing.PaymentApiTests.provider_result
    initialize_url = existing.PaymentApiTests.initialize_url
    verify_url = existing.PaymentApiTests.verify_url

    def setUp(self):
        # Prepare fixtures through the real API with the gate disabled only in
        # this local test, then exercise the enabled gate with a real session.
        with override_settings(STAGING_DIC_TESTER_RESTRICTION_ENABLED=False):
            existing.PaymentApiTests.setUp(self)
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_superuser(
            username="DIF", email="tester@example.test", password="test-only"
        )

    def sign_in(self, username="DIF", password="test-only"):
        self.client.get("/api/v1/dic/tester-access/login/")
        csrf = self.client.cookies["csrftoken"].value
        response = self.client.post("/api/v1/dic/tester-access/login/", {
            "username": username, "password": password,
        }, HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 302)
        return self.client.cookies["csrftoken"].value

    def test_anonymous_direct_render_mutations_are_denied_even_with_bearer(self):
        attempt = self.create_pending_attempt()
        for path in ("/api/v1/dic/orders/", self.initialize_url(),
                     self.verify_url(attempt.reference),
                     f"/api/v1/dic/orders/{self.order_id}/pricing/accept/"):
            response = self.client.post(path, {}, format="json", **self.auth,
                                        HTTP_HOST="backend-staging.onrender.com")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["code"], "staging_tester_required")
            self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(RegistrationOrder.objects.count(), 1)
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_allowlist_and_tester_group_are_both_required(self):
        self.client.force_login(self.user)
        with override_settings(STAGING_DIC_TESTER_USERNAMES=[]):
            self.assertEqual(self.client.post("/api/v1/dic/orders/", {}).status_code, 403)
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        response = self.client.post("/api/v1/dic/orders/", {})
        self.assertEqual(response.json()["code"], "staging_tester_required")

    def test_authorized_session_requires_csrf(self):
        self.sign_in()
        response = self.client.post(self.initialize_url(), {}, **self.auth)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staging_tester_csrf_required")

    def test_cross_origin_post_is_rejected_even_with_session_and_csrf(self):
        csrf = self.sign_in()
        response = self.client.post(self.initialize_url(), {}, **self.auth,
            HTTP_X_CSRFTOKEN=csrf, HTTP_ORIGIN="https://untrusted.example.test")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "staging_tester_csrf_required")

    def test_logout_revokes_tester_access_even_with_valid_order_bearer(self):
        csrf = self.sign_in()
        self.assertEqual(self.client.post("/api/v1/dic/tester-access/logout/", {},
            HTTP_X_CSRFTOKEN=csrf).status_code, 302)
        response = self.client.post(self.initialize_url(), {}, **self.auth,
                                    HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.json()["code"], "staging_tester_required")

    def test_tester_can_create_initialize_and_verify_normal_flow(self):
        csrf = self.sign_in()
        response = self.client.post("/api/v1/dic/orders/", self.order_payload, format="json",
            HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201)
        order_id, token = response.data["order_id"], response.data["access_token"]
        headers = {"HTTP_X_CSRFTOKEN": csrf, "HTTP_AUTHORIZATION": f"Bearer {token}"}
        with patch("dic.payment_views.PaystackClient") as factory:
            factory.return_value.initialize_transaction.side_effect = lambda **kw: {
                "reference": kw["reference"],
                "authorization_url": "https://checkout.paystack.com/test-access",
            }
            init = self.client.post(self.initialize_url(order_id), {}, **headers)
            self.assertEqual(init.status_code, 200)
            ref = init.data["payment_reference"]
            factory.return_value.verify_transaction.return_value = self.provider_result(ref)
            verified = self.client.post(
                f"/api/v1/dic/orders/{order_id}/payments/{ref}/verify/", {}, **headers)
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.data["payment_status"], "paid")

    def test_tester_session_does_not_replace_order_bearer(self):
        csrf = self.sign_in()
        self.assertEqual(self.client.post(self.initialize_url(), {},
            HTTP_X_CSRFTOKEN=csrf).status_code, 404)

    def test_draft_edition_is_still_closed_to_testers(self):
        csrf = self.sign_in()
        self.edition.registration_status = "draft"
        self.edition.save(update_fields=["registration_status"])
        response = self.client.post("/api/v1/dic/orders/", self.order_payload, format="json",
            HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(RegistrationOrder.objects.count(), 1)

    def test_bearer_confirmation_and_recovery_options_remain_available(self):
        detail = self.client.get(f"/api/v1/dic/orders/{self.order_id}/", **self.auth)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/dic/recovery/channels/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/dic/registration-options/").status_code, 200)

    def test_signed_webhook_remains_accessible_without_tester_session(self):
        attempt = self.create_pending_attempt()
        body = json.dumps({"event": "charge.success", "data": {
            "reference": attempt.reference}}).encode()
        path = "/api/v1/dic/payments/paystack/webhook/"
        invalid = self.client.post(path, body, content_type="application/json",
                                  HTTP_X_PAYSTACK_SIGNATURE="invalid")
        self.assertEqual(invalid.status_code, 400)
        signature = hmac.new(b"sk_test_unit_mock", body, hashlib.sha512).hexdigest()
        with patch("dic.payment_views.PaystackClient") as factory:
            factory.return_value.secret_key = "sk_test_unit_mock"
            factory.return_value.verify_transaction.return_value = self.provider_result(attempt.reference)
            response = self.client.post(path, body, content_type="application/json",
                                       HTTP_X_PAYSTACK_SIGNATURE=signature)
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")

    def test_disabling_gate_restores_public_bearer_flow(self):
        with override_settings(STAGING_DIC_TESTER_RESTRICTION_ENABLED=False):
            response = self.client.post("/api/v1/dic/orders/", self.order_payload, format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201)

    def test_production_middleware_has_no_tester_gate(self):
        import os
        from pathlib import Path
        import subprocess
        import sys

        # Import real production declarations only in a synthetic subprocess.
        # Never read dotenv, connect, or pollute this suite's imported settings.
        backend = Path(__file__).resolve().parents[1]
        code = (
            'import sys,socket;sys.path.insert(0,' + repr(str(backend)) + ');'
            'from unittest.mock import patch;import environ;'
            'from django.db.backends.base.base import BaseDatabaseWrapper;'
            'deny=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("I/O forbidden"));'
            'socket.socket.connect=deny;socket.create_connection=deny;'
            'BaseDatabaseWrapper.ensure_connection=deny;'
            'guard=patch.object(environ.Env,"read_env");guard.start();'
            'from config.settings import production;import json;'
            'print(json.dumps(production.MIDDLEWARE))'
        )
        env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'PATH') if key in os.environ}
        env.update(DJANGO_SETTINGS_MODULE='config.settings.production',
            DJANGO_SECRET_KEY='synthetic-production-settings-test-' * 3,
            DJANGO_ALLOWED_HOSTS='backend.example.test',
            DATABASE_URL='postgresql://synthetic:unused@database.example.test/synthetic_settings_only',
            PAYSTACK_MODE='test', PAYSTACK_SECRET_KEY='', DIC_MEMORY_STORAGE='disabled')
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code], env=env,
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        middleware = json.loads(result.stdout)

        self.assertNotIn("config.staging_tester_access.DICStagingTesterMiddleware",
                         middleware)
        with override_settings(MIDDLEWARE=middleware):
            response = APIClient().post("/api/v1/dic/orders/", self.order_payload, format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201)

    def create_ordinary_tester(self, index):
        user = get_user_model().objects.create_user(
            username=f"dic-tester-{index:02d}", password=f"test-only-{index}",
            is_staff=False, is_superuser=False,
        )
        group, _ = Group.objects.get_or_create(name="DIC Staging Testers")
        user.groups.add(group)
        return user

    def test_supervisor_and_nine_individual_testers_can_create_and_pay(self):
        # Exercise all ten separate password logins and normal payment flows.
        for index in range(10):
            with self.subTest(tester=index):
                user = self.user if index == 0 else self.create_ordinary_tester(index)
                self.client = APIClient(enforce_csrf_checks=True)
                csrf = self.sign_in(user.username, "test-only" if index == 0 else f"test-only-{index}")
                self.assertEqual(self.client.get("/api/v1/dic/tester-access/login/").status_code, 200)
                created = self.client.post("/api/v1/dic/orders/", self.order_payload, format="json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()), HTTP_X_CSRFTOKEN=csrf)
                self.assertEqual(created.status_code, 201)
                order_id = created.data["order_id"]
                headers = {"HTTP_X_CSRFTOKEN": csrf,
                    "HTTP_AUTHORIZATION": f"Bearer {created.data['access_token']}"}
                with patch("dic.payment_views.PaystackClient") as factory:
                    factory.return_value.initialize_transaction.side_effect = lambda **kw: {
                        "reference": kw["reference"],
                        "authorization_url": "https://checkout.paystack.com/test-access",
                    }
                    init = self.client.post(self.initialize_url(order_id), {}, **headers)
                    self.assertEqual(init.status_code, 200)
                    ref = init.data["payment_reference"]
                    factory.return_value.verify_transaction.return_value = self.provider_result(ref, id=5000 + index)
                    paid = self.client.post(f"/api/v1/dic/orders/{order_id}/payments/{ref}/verify/", {}, **headers)
                self.assertEqual(paid.data["payment_status"], "paid")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_superuser)
        self.assertEqual(Group.objects.get(name="DIC Staging Testers").permissions.count(), 0)

    def test_ordinary_tester_has_no_admin_operations_or_finance_access(self):
        user = self.create_ordinary_tester(1)
        csrf = self.sign_in(user.username, "test-only-1")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_perm("dic.can_view_dic_operations"))
        self.assertFalse(user.has_perm("dic.can_view_dic_finance"))
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.assertEqual(self.client.get("/admin/dic/operations/").status_code, 302)
        for route in ("auth/me/", "dashboard/", "registrations/", "payments/"):
            self.assertEqual(self.client.get(f"/api/v1/dic/operations/{route}").status_code, 403)
        ops_login = self.client.post("/api/v1/dic/operations/auth/login/", {
            "username": user.username, "password": "test-only-1",
        }, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(ops_login.status_code, 401)

    def test_group_without_allowlist_and_allowlist_without_group_cannot_log_in(self):
        self.create_ordinary_tester(1)
        for allowed, grouped in (([], True), (["dic-tester-01"], False)):
            if not grouped:
                get_user_model().objects.get(username="dic-tester-01").groups.clear()
            with override_settings(STAGING_DIC_TESTER_USERNAMES=allowed):
                self.client.get("/api/v1/dic/tester-access/login/")
                csrf = self.client.cookies["csrftoken"].value
                response = self.client.post("/api/v1/dic/tester-access/login/", {
                    "username": "dic-tester-01", "password": "test-only-1",
                }, HTTP_X_CSRFTOKEN=csrf)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_is_csrf_protected_and_throttled(self):
        self.client.get("/api/v1/dic/tester-access/login/")
        self.assertEqual(self.client.post("/api/v1/dic/tester-access/login/", {
            "username": "DIF", "password": "test-only",
        }).status_code, 403)
        csrf = self.client.cookies["csrftoken"].value
        rates = {**settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "dic_staging_tester_login": "1/hour"}
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}):
            first = self.client.post("/api/v1/dic/tester-access/login/", {
                "username": "DIF", "password": "wrong",
            }, HTTP_X_CSRFTOKEN=csrf)
            second = self.client.post("/api/v1/dic/tester-access/login/", {
                "username": "DIF", "password": "wrong",
            }, HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_production_has_no_tester_login_route(self):
        with override_settings(ROOT_URLCONF="config.urls"):
            self.assertEqual(self.client.get("/api/v1/dic/tester-access/login/").status_code, 404)

    def test_admin_created_ordinary_account_logs_in_without_staff_or_operations_permissions(self):
        from config.staging_tester_access import is_staging_tester
        from config.staging_tester_views import TesterAuthenticationForm

        group, _ = Group.objects.get_or_create(name="DIC Staging Testers")
        self.client.force_login(self.user)
        csrf = self.client.get("/api/v1/dic/operations/auth/csrf/").json()["csrfToken"]
        password = "Cedar-lantern-copper-93!"
        created = self.client.post("/admin/accounts/user/add/", {
            "username": "dic-tester-01", "usable_password": "true",
            "password1": password, "password2": password, "_save": "Save",
        }, HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(created.status_code, 302)
        user = get_user_model().objects.get(username="dic-tester-01")
        self.assertTrue(user.is_active)
        self.assertTrue(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        # The standard creation form does not automatically assign the tester
        # group. Creating the group itself also does not add this user to it.
        self.assertFalse(is_staging_tester(user))
        user.groups.add(group)
        self.assertFalse(user.has_perm("dic.can_view_dic_operations"))
        self.assertTrue(is_staging_tester(user))
        self.assertEqual(authenticate(username=user.username, password=password).pk, user.pk)
        form = TesterAuthenticationForm(data={"username": user.username, "password": password})
        self.assertTrue(form.is_valid(), form.errors)
        self.client = APIClient(enforce_csrf_checks=True)
        csrf = self.sign_in(user.username, password)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        response = self.client.post("/api/v1/dic/orders/", self.order_payload, format="json",
            HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201)

    def test_each_missing_ordinary_tester_requirement_rejects_login(self):
        from config.staging_tester_access import is_staging_tester

        user = self.create_ordinary_tester(1)
        group = Group.objects.get(name="DIC Staging Testers")
        wrong_group = Group.objects.create(name="DIC staging testers")
        cases = (
            "wrong_password", "unusable_password", "inactive", "missing_group",
            "wrong_group_case", "missing_allowlist", "allowlist_leading_space",
            "allowlist_wrong_case", "wrong_username",
        )
        for missing in cases:
            with self.subTest(missing=missing):
                user.is_active = missing != "inactive"
                user.set_password("test-only-1")
                if missing == "unusable_password":
                    user.set_unusable_password()
                user.save(update_fields=["is_active", "password"])
                user.groups.set([] if missing == "missing_group" else
                                [wrong_group] if missing == "wrong_group_case" else [group])
                allowed = {"missing_allowlist": ["DIF"],
                           "allowlist_leading_space": ["DIF", " dic-tester-01"],
                           "allowlist_wrong_case": ["DIF", "DIC-TESTER-01"]}.get(
                               missing, ["DIF", "dic-tester-01"])
                username = "DIC-TESTER-01" if missing == "wrong_username" else user.username
                password = "wrong-password" if missing == "wrong_password" else "test-only-1"
                self.client = APIClient(enforce_csrf_checks=True)
                self.client.get("/api/v1/dic/tester-access/login/")
                csrf = self.client.cookies["csrftoken"].value
                with override_settings(STAGING_DIC_TESTER_USERNAMES=allowed):
                    response = self.client.post("/api/v1/dic/tester-access/login/", {
                        "username": username, "password": password,
                    }, HTTP_X_CSRFTOKEN=csrf)
                    self.assertEqual(response.status_code, 200)
                    self.assertNotIn("_auth_user_id", self.client.session)
                    if missing not in ("wrong_password", "unusable_password", "wrong_username"):
                        self.assertFalse(is_staging_tester(user))

    def test_existing_session_loses_access_when_membership_allowlist_or_active_status_is_removed(self):
        user = self.create_ordinary_tester(1)
        group = Group.objects.get(name="DIC Staging Testers")
        for missing in ("group", "allowlist", "active"):
            with self.subTest(missing=missing):
                user.is_active = True
                user.save(update_fields=["is_active"])
                user.groups.set([group])
                self.client = APIClient(enforce_csrf_checks=True)
                csrf = self.sign_in(user.username, "test-only-1")
                if missing == "group":
                    user.groups.clear()
                if missing == "active":
                    user.is_active = False
                    user.save(update_fields=["is_active"])
                allowed = [] if missing == "allowlist" else [user.username]
                with override_settings(STAGING_DIC_TESTER_USERNAMES=allowed):
                    response = self.client.post(self.initialize_url(), {}, **self.auth,
                                                HTTP_X_CSRFTOKEN=csrf)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["code"], "staging_tester_required")
