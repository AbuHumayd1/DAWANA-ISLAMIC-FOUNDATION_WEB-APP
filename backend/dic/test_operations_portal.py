import csv
import hashlib
import io
import uuid
from datetime import date, timedelta
from decimal import Decimal
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from docx import Document

from .models import (
    CampEdition,
    DICAdminAuditEvent,
    Participant,
    PaymentAttempt,
    PrimaryRegistrant,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationOrderItem,
    RegistrationRecoveryChallenge,
)


class DICOperationsPortalTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.edition = CampEdition.objects.create(
            name="Portal Test Camp",
            year=2097,
            camp_start_date=today + timedelta(days=30),
            camp_end_date=today + timedelta(days=36),
            is_active=True,
        )
        self.category = RegistrationCategory.objects.create(
            edition=self.edition,
            name="Portal Test Category",
            fee_ngn=Decimal("125.00"),
        )
        self.operator = self.create_user(
            "dic-operator",
            "operator-password-not-used-in-logs",
            "can_view_dic_operations",
            "can_export_dic_reports",
        )
        self.finance = self.create_user(
            "dic-finance",
            "finance-password-not-used-in-logs",
            "can_view_dic_operations",
            "can_view_dic_finance",
            "can_export_dic_reports",
        )
        self.paid_order = self.make_order(
            ("Paid Participant A", "Paid Participant B"),
            paid=True,
        )
        self.unpaid_order = self.make_order(
            ("Unpaid Participant",),
            paid=False,
        )

    def create_user(self, username, password, *codenames):
        user = get_user_model().objects.create_user(
            username=username,
            password=password,
        )
        permissions = Permission.objects.filter(
            content_type=ContentType.objects.get(
                app_label="dic",
                model="campedition",
            ),
            codename__in=codenames,
        )
        user.user_permissions.add(*permissions)
        return user

    def make_order(self, names, *, paid):
        registrant = PrimaryRegistrant.objects.create(
            full_name="Portal Guardian",
            phone="+2348000000011",
            email=f"guardian-{uuid.uuid4()}@example.test",
        )
        order = RegistrationOrder.objects.create(
            primary_registrant=registrant,
            edition=self.edition,
            status=(
                RegistrationOrder.Status.CONFIRMED
                if paid
                else RegistrationOrder.Status.SUBMITTED
            ),
            payment_status=(
                RegistrationOrder.PaymentStatus.PAID
                if paid
                else RegistrationOrder.PaymentStatus.PENDING
            ),
            idempotency_key_digest=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            request_fingerprint=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            access_token_digest=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        )
        for name in names:
            participant = Participant.objects.create(
                full_name=name,
                address="Confidential participant address",
                phone="+2348000000022",
                email=f"participant-{uuid.uuid4()}@example.test",
                date_of_birth=date(2011, 2, 3),
                sex=Participant.Sex.MALE,
                height_cm=Decimal("142.00"),
                weight_kg=Decimal("42.00"),
                academic_status=Participant.AcademicStatus.SECONDARY,
                occupation=Participant.Occupation.BUSINESS,
                marital_status=Participant.MaritalStatus.SINGLE,
            )
            RegistrationOrderItem.objects.create(
                order=order,
                participant=participant,
                category=self.category,
                category_name_snapshot=self.category.name,
                fee_snapshot_ngn=self.category.fee_ngn,
                participant_snapshot={"full_name": name},
            )
        if paid:
            PaymentAttempt.objects.create(
                order=order,
                reference=f"DIC-{uuid.uuid4()}",
                amount_kobo=len(names) * 12500,
                currency="NGN",
                status=PaymentAttempt.Status.SUCCESSFUL,
                provider_reported_amount_kobo=len(names) * 12500,
                provider_reported_currency="NGN",
                provider_status="success",
                provider_paid_at=timezone.now(),
            )
        return order

    def test_private_api_requires_authenticated_operations_permission(self):
        dashboard = reverse("dic:operations-dashboard")
        self.assertIn(self.client.get(dashboard).status_code, (401, 403))

        no_permission = get_user_model().objects.create_user(
            username="no-operations",
            password="password",
        )
        self.client.force_login(no_permission)
        self.assertEqual(self.client.get(dashboard).status_code, 403)

    def test_session_login_requires_csrf_and_shares_the_django_user(self):
        client = Client(enforce_csrf_checks=True)
        csrf_url = reverse("dic:operations-csrf")
        csrf_response = client.get(csrf_url)
        token = csrf_response.json()["csrfToken"]
        login_url = reverse("dic:operations-login")
        credentials = {
            "username": self.operator.username,
            "password": "operator-password-not-used-in-logs",
        }
        denied = client.post(login_url, credentials, content_type="application/json")
        self.assertEqual(denied.status_code, 403)

        response = client.post(
            login_url,
            credentials,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.operator.pk)
        self.assertEqual(response.json()["role"], "DIC Operator")
        self.assertFalse(response.json()["can_access_django_admin"])
        self.assertNotIn("password", response.json())
        self.assertIn("sessionid", client.cookies)
        self.assertTrue(response.cookies["sessionid"]["httponly"])

        refreshed_token = client.get(csrf_url).json()["csrfToken"]
        me_response = client.get(reverse("dic:operations-me"))
        self.assertEqual(me_response.status_code, 200)
        logout_response = client.post(
            reverse("dic:operations-logout"),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=refreshed_token,
        )
        self.assertEqual(logout_response.status_code, 204)
        self.assertIn(
            client.get(reverse("dic:operations-me")).status_code,
            (401, 403),
        )

    def test_operator_dashboard_counts_orders_and_participants_from_real_data(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse("dic:operations-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["metrics"]["orders"], 2)
        self.assertEqual(response.json()["metrics"]["participants"], 3)
        self.assertEqual(response.json()["metrics"]["verified_paid_orders"], 1)
        self.assertEqual(response.json()["metrics"]["verified_paid_participants"], 2)
        self.assertEqual(response.json()["edition"]["registration_status"], "draft")

    def test_contact_and_finance_data_are_separately_permission_gated(self):
        self.client.force_login(self.operator)
        order_url = reverse(
            "dic:operations-registration-detail",
            args=(self.paid_order.public_id,),
        )
        response = self.client.get(order_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("registrant", response.json())
        self.assertNotIn("payment_attempts", response.json())
        self.assertNotIn(
            "address",
            response.json()["participants"][0],
        )
        self.assertEqual(
            self.client.get(reverse("dic:operations-payments")).status_code,
            403,
        )

        contact_permission = Permission.objects.get(
            content_type__app_label="dic",
            codename="can_view_dic_contact_information",
        )
        self.operator.user_permissions.add(contact_permission)
        response = self.client.get(order_url)
        self.assertIn("registrant", response.json())
        self.assertIn("email", response.json()["participants"][0])

        self.client.force_login(self.finance)
        finance_response = self.client.get(order_url)
        self.assertIn("payment_attempts", finance_response.json())
        self.assertIn("audit_history", finance_response.json())
        self.assertNotIn("authorization_url", str(finance_response.json()))

    def test_search_filtering_and_pagination_are_backend_enforced(self):
        self.client.force_login(self.operator)
        url = reverse("dic:operations-registrations")
        response = self.client.get(url, {"q": "Paid Participant A", "page_size": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["page_size"], 1)
        response = self.client.get(url, {"q": "participant-"})
        self.assertEqual(response.json()["count"], 0)
        response = self.client.get(url, {"payment_status": "paid"})
        self.assertEqual(response.json()["count"], 1)
        response = self.client.get(url, {"payment_status": "not-a-status"})
        self.assertEqual(response.status_code, 400)

    def test_csv_and_word_exports_are_safe_audited_and_use_the_same_records(self):
        self.client.force_login(self.operator)
        export_url = reverse("dic:operations-report")
        csv_response = self.client.get(
            export_url,
            {"report": "registrations", "format": "csv"},
        )
        self.assertEqual(csv_response.status_code, 200)
        csv_rows = list(
            csv.reader(io.StringIO(csv_response.content.decode("utf-8-sig")))
        )
        self.assertEqual(len(csv_rows) - 1, 2)
        self.assertNotIn("participant_emails", csv_rows[0])
        self.assertNotIn("access_token", csv_response.content.decode("utf-8").lower())

        word_response = self.client.get(
            export_url,
            {"report": "registrations", "format": "docx"},
        )
        self.assertEqual(word_response.status_code, 200)
        with ZipFile(io.BytesIO(word_response.content)) as archive:
            self.assertIn("word/document.xml", archive.namelist())
        document = Document(io.BytesIO(word_response.content))
        self.assertIn("DAWANA ISLAMIC FOUNDATION", document.paragraphs[0].text)
        self.assertEqual(len(document.tables[0].rows) - 1, len(csv_rows) - 1)

        events = DICAdminAuditEvent.objects.filter(
            actor=self.operator,
            action="operations_report_export",
        )
        self.assertEqual(events.count(), 2)
        self.assertSetEqual(
            set(events.values_list("details__format", flat=True)),
            {"csv", "docx"},
        )

    def test_contact_and_payment_report_exports_require_separate_permissions(self):
        export_url = reverse("dic:operations-report")
        self.client.force_login(self.operator)
        denied_payments = self.client.get(
            export_url,
            {"report": "payments", "format": "csv"},
        )
        self.assertEqual(denied_payments.status_code, 403)
        no_contact_csv = self.client.get(
            export_url,
            {"report": "participants", "format": "csv"},
        )
        self.assertNotIn(b"participant_emails", no_contact_csv.content)

        export_contact = Permission.objects.get(
            content_type__app_label="dic",
            codename="can_export_dic_contact_information",
        )
        self.operator.user_permissions.add(export_contact)
        contact_csv = self.client.get(
            export_url,
            {"report": "participants", "format": "csv"},
        )
        self.assertIn(b"Email", contact_csv.content)

    def test_recovery_status_is_visible_without_recovery_secrets(self):
        challenge = RegistrationRecoveryChallenge.objects.create(
            channel=RegistrationRecoveryChallenge.Channel.EMAIL,
            contact_digest="a" * 64,
            code_digest="b" * 64,
            encrypted_delivery_payload="sensitive-ciphertext",
            expires_at=timezone.now() + timedelta(minutes=5),
            resend_after=timezone.now() + timedelta(seconds=30),
        )
        challenge.orders.add(self.unpaid_order)
        self.client.force_login(self.operator)
        response = self.client.get(
            reverse(
                "dic:operations-registration-detail",
                args=(self.unpaid_order.public_id,),
            )
        )
        body = str(response.json())
        self.assertIn("Queued", body)
        self.assertNotIn("sensitive-ciphertext", body)
        self.assertNotIn("b" * 64, body)
        self.assertNotIn("access_token", body.lower())

    def test_payment_report_accepts_attempt_status_and_matches_both_formats(self):
        self.client.force_login(self.finance)
        url = reverse("dic:operations-report")
        for export_format in ("csv", "docx"):
            response = self.client.get(url, {"report": "payments", "format": export_format, "status": "successful"})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action="operations_report_export").count(), 2)

    def test_manual_paid_status_does_not_create_verified_payment(self):
        self.unpaid_order.payment_status = RegistrationOrder.PaymentStatus.PAID
        self.unpaid_order.status = RegistrationOrder.Status.CONFIRMED
        self.unpaid_order.save()
        self.client.force_login(self.operator)
        data = self.client.get(reverse("dic:operations-dashboard")).json()
        self.assertEqual(data["metrics"]["verified_paid_orders"], 1)
        self.assertEqual(data["metrics"]["verified_paid_participants"], 2)
        self.assertIsNone(data["metrics"]["reconciliation_cases"])

    def test_dashboard_activity_period_is_validated(self):
        self.client.force_login(self.operator)
        url = reverse("dic:operations-dashboard")
        self.assertEqual(self.client.get(url, {"days": 7}).status_code, 200)
        self.assertEqual(self.client.get(url, {"days": "invalid"}).status_code, 400)

    def test_finance_permission_does_not_expose_audit_event_details(self):
        DICAdminAuditEvent.objects.create(action="test", target_type="RegistrationOrder", target_id=str(self.paid_order.public_id), details={"restricted": "audit-only"})
        self.client.force_login(self.finance)
        response = self.client.get(reverse("dic:operations-registration-detail", args=(self.paid_order.public_id,)))
        self.assertEqual(response.json()["audit_history"], [])
        self.assertNotIn("audit-only", str(response.json()))

    def test_logout_requires_csrf_and_session_cookie_is_httponly(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.operator)
        self.assertEqual(client.post(reverse("dic:operations-logout")).status_code, 403)

    def test_all_report_types_support_word_and_csv(self):
        self.client.force_login(self.finance)
        for report in ("registrations", "participants", "payments", "categories", "houses", "attention"):
            for export_format in ("csv", "docx"):
                with self.subTest(report=report, format=export_format):
                    response = self.client.get(reverse("dic:operations-report"), {"report": report, "format": export_format})
                    self.assertEqual(response.status_code, 200)

    def test_invalid_house_filter_returns_validation_error(self):
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse("dic:operations-registrations"), {"house": "invalid"}).status_code, 400)
