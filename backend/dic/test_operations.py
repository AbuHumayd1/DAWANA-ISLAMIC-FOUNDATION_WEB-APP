import csv
import hashlib
import io
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    CampEdition,
    DICAdminAuditEvent,
    House,
    HouseAllocation,
    PaymentAttempt,
    Participant,
    PrimaryRegistrant,
    RegistrationCategory,
    RegistrationOrder,
    RegistrationOrderItem,
    RegistrationRecoveryChallenge,
)


class DICOperationsTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.edition = CampEdition.objects.create(
            name="Operations Test Camp",
            year=2098,
            camp_start_date=today + timedelta(days=30),
            camp_end_date=today + timedelta(days=36),
            is_active=True,
        )
        self.category = RegistrationCategory.objects.create(
            edition=self.edition,
            name="Operations Test Category",
            fee_ngn=Decimal("100.00"),
        )
        self.paid_order = self.make_order(
            ("=HYPERLINK(\"https://invalid.test\")", "Second Participant"),
            paid=True,
        )
        self.unpaid_order = self.make_order(("Unpaid Participant",), paid=False)

    def permission(self, codename, model="campedition"):
        content_type = ContentType.objects.get(
            app_label="dic",
            model=model,
        )
        return Permission.objects.get(
            content_type=content_type,
            codename=codename,
        )

    def make_staff(self, username, *permissions):
        user = get_user_model().objects.create_user(
            username=username,
            is_staff=True,
        )
        user.user_permissions.add(*permissions)
        return user

    def make_order(self, participant_names, *, paid):
        registrant = PrimaryRegistrant.objects.create(
            full_name="Operations Guardian",
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
        for name in participant_names:
            participant = Participant.objects.create(
                full_name=name,
                address="Test address",
                phone="+2348000000000",
                email=f"{uuid.uuid4()}@example.test",
                date_of_birth=date(2010, 1, 1),
                sex=Participant.Sex.MALE,
                height_cm=Decimal("140.00"),
                weight_kg=Decimal("40.00"),
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
                amount_kobo=len(participant_names) * 10000,
                status=PaymentAttempt.Status.SUCCESSFUL,
                provider_reported_amount_kobo=len(participant_names) * 10000,
                provider_reported_currency="NGN",
                provider_paid_at=timezone.now(),
            )
        return order

    def test_operations_dashboard_requires_staff_authentication_and_permission(self):
        url = reverse("dic_operations_dashboard")
        anonymous = self.client.get(url)
        self.assertEqual(anonymous.status_code, 302)

        staff = self.make_staff("no-dic-ops")
        self.client.force_login(staff)
        forbidden = self.client.get(url)
        self.assertEqual(forbidden.status_code, 403)

    def test_dashboard_distinguishes_orders_from_multi_participant_counts(self):
        unverified_paid = self.make_order(
            ("Unverified Participant",),
            paid=False,
        )
        RegistrationOrder.objects.filter(pk=unverified_paid.pk).update(
            status=RegistrationOrder.Status.CONFIRMED,
            payment_status=RegistrationOrder.PaymentStatus.PAID,
        )
        staff = self.make_staff(
            "registration-ops",
            self.permission("can_view_dic_operations"),
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("dic_operations_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_orders"], 3)
        self.assertEqual(response.context["individual_participants"], 4)
        self.assertEqual(response.context["verified_paid_orders"], 1)
        self.assertEqual(response.context["verified_paid_participants"], 2)
        self.assertEqual(response.context["unpaid_orders"], 1)
        self.assertEqual(response.context["attention_count"], 2)
        self.assertContains(response, "Registration orders")
        self.assertContains(response, "Individual participants")
        self.assertNotIn("reconciliation_count", response.context)

    def test_order_detail_shows_recovery_status_without_tokens_or_contact_data(self):
        challenge = RegistrationRecoveryChallenge.objects.create(
            channel=RegistrationRecoveryChallenge.Channel.EMAIL,
            contact_digest="a" * 64,
            code_digest="b" * 64,
            encrypted_delivery_payload="encrypted-sensitive-payload",
            expires_at=timezone.now() + timedelta(minutes=5),
            resend_after=timezone.now() + timedelta(seconds=60),
        )
        challenge.orders.add(self.paid_order)
        staff = self.make_staff(
            "registration-order-view",
            self.permission("view_registrationorder", "registrationorder"),
        )
        self.client.force_login(staff)

        response = self.client.get(
            reverse(
                "admin:dic_registrationorder_change",
                args=(self.paid_order.pk,),
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Queued")
        self.assertContains(response, str(self.paid_order.public_id))
        self.assertNotContains(response, "encrypted-sensitive-payload")
        self.assertNotContains(response, "b" * 64)
        self.assertNotContains(response, self.paid_order.items.first().participant.email)

    def test_reconciliation_is_visible_only_to_finance_authorized_staff(self):
        PaymentAttempt.objects.create(
            order=self.unpaid_order,
            reference=f"DIC-{uuid.uuid4()}",
            amount_kobo=10000,
            status=PaymentAttempt.Status.RECONCILIATION_REQUIRED,
            failure_code="provider_paid_at_missing_or_invalid",
        )
        staff = self.make_staff(
            "finance-ops",
            self.permission("can_view_dic_operations"),
            self.permission("can_view_dic_finance"),
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("dic_operations_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["reconciliation_count"], 1)
        self.assertContains(response, "Payment reconciliation cases")
        self.assertEqual(response.context["unverified_paid_status_count"], 0)

        unverified_paid = self.make_order(("Marked paid without proof",), paid=False)
        RegistrationOrder.objects.filter(pk=unverified_paid.pk).update(
            payment_status=RegistrationOrder.PaymentStatus.PAID,
            status=RegistrationOrder.Status.CONFIRMED,
        )
        response = self.client.get(reverse("dic_operations_dashboard"))
        self.assertEqual(response.context["verified_paid_orders"], 1)
        self.assertEqual(response.context["unverified_paid_status_count"], 1)

    def test_registration_search_and_category_house_filters_are_available(self):
        staff = self.make_staff(
            "registration-search",
            self.permission("view_registrationorder", "registrationorder"),
        )
        self.client.force_login(staff)
        url = reverse("admin:dic_registrationorder_changelist")

        search = self.client.get(url, {"q": "Second Participant"})
        self.assertEqual(search.status_code, 200)
        self.assertContains(search, str(self.paid_order.public_id))

        category_filter = self.client.get(
            url,
            {"registration_category": self.category.pk},
        )
        self.assertEqual(category_filter.status_code, 200)
        self.assertContains(category_filter, str(self.paid_order.public_id))
        self.assertContains(category_filter, str(self.unpaid_order.public_id))

        house = House.objects.create(
            edition=self.edition,
            name="Configured Test House",
            gender=House.Gender.MALE,
            capacity=10,
        )
        participant = self.paid_order.items.first().participant
        HouseAllocation.objects.create(
            participant=participant,
            edition=self.edition,
            house=house,
        )
        house_filter = self.client.get(url, {"allocated_house": house.pk})
        self.assertEqual(house_filter.status_code, 200)
        self.assertContains(house_filter, str(self.paid_order.public_id))
        self.assertNotContains(house_filter, str(self.unpaid_order.public_id))

    def test_participant_directory_filters_by_category_house_and_verified_payment(self):
        staff = self.make_staff(
            "participant-directory",
            self.permission("view_participant", "participant"),
        )
        self.client.force_login(staff)
        url = reverse("admin:dic_participant_changelist")

        paid_participant = self.paid_order.items.first().participant
        paid_filter = self.client.get(url, {"verified_payment_status": "paid"})
        self.assertEqual(paid_filter.status_code, 200)
        self.assertEqual(paid_filter.context["cl"].result_count, 2)
        self.assertContains(paid_filter, "Second Participant")
        self.assertNotContains(paid_filter, "Unpaid Participant")

        category_filter = self.client.get(
            url,
            {"registration_category": self.category.pk},
        )
        self.assertEqual(category_filter.status_code, 200)
        self.assertEqual(category_filter.context["cl"].result_count, 3)

        house = House.objects.create(
            edition=self.edition,
            name="Directory Filter House",
            gender=House.Gender.MALE,
            capacity=10,
        )
        HouseAllocation.objects.create(
            participant=paid_participant,
            edition=self.edition,
            house=house,
        )
        house_filter = self.client.get(url, {"allocated_house": house.pk})
        self.assertEqual(house_filter.status_code, 200)
        self.assertEqual(house_filter.context["cl"].result_count, 1)
        self.assertNotContains(house_filter, "Unpaid Participant")

    def test_contact_search_is_only_enabled_with_contact_permission(self):
        without_contact = self.make_staff(
            "no-contact-search",
            self.permission("view_registrationorder", "registrationorder"),
        )
        with_contact = self.make_staff(
            "contact-search",
            self.permission("view_registrationorder", "registrationorder"),
            self.permission("can_view_dic_contact_information"),
        )
        model_admin = admin.site._registry[RegistrationOrder]

        request = type("Request", (), {"user": without_contact})()
        self.assertNotIn("items__participant__email", model_admin.get_search_fields(request))
        request.user = with_contact
        self.assertIn("items__participant__email", model_admin.get_search_fields(request))

    def test_csv_export_requires_permission_and_is_formula_safe(self):
        export_permission = self.permission("can_export_dic_reports")
        view_permission = self.permission(
            "view_registrationorder",
            "registrationorder",
        )
        staff = self.make_staff(
            "report-export",
            export_permission,
            view_permission,
        )
        self.client.force_login(staff)
        url = reverse("admin:dic_registrationorder_changelist")

        response = self.client.post(
            url,
            {
                "action": "export_selected_orders_csv",
                "_selected_action": [self.paid_order.pk],
                "index": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(rows[0][0], "order_reference")
        self.assertNotIn("participant_names", rows[0])
        self.assertNotIn("=HYPERLINK", response.content.decode("utf-8"))
        audit = DICAdminAuditEvent.objects.get(action="registration_export")
        self.assertEqual(audit.actor, staff)
        self.assertFalse(audit.details["contact_information_included"])

        staff.user_permissions.add(
            self.permission("can_export_dic_contact_information"),
        )
        response = self.client.post(
            url,
            {
                "action": "export_selected_orders_csv",
                "_selected_action": [self.paid_order.pk],
                "index": "0",
            },
        )
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8"))))
        self.assertIn("participant_names", rows[0])
        participant_names = rows[1][rows[0].index("participant_names")]
        self.assertTrue(participant_names.startswith("'=HYPERLINK"))
        self.assertTrue(
            DICAdminAuditEvent.objects.filter(
                action="registration_export",
                details__contact_information_included=True,
            ).exists()
        )

    def test_manual_payment_status_changes_are_not_allowed_in_admin(self):
        from django.contrib import admin

        staff = self.make_staff(
            "finance-readonly",
            self.permission("view_registrationorder", "registrationorder"),
        )
        model_admin = admin.site._registry[RegistrationOrder]
        request = type("Request", (), {"user": staff, "method": "POST"})()
        self.assertFalse(model_admin.has_change_permission(request, self.unpaid_order))
        request.method = "GET"
        self.assertIn("payment_status", model_admin.get_readonly_fields(request))

        self.client.force_login(staff)
        response = self.client.post(
            reverse(
                "admin:dic_registrationorder_change",
                args=(self.unpaid_order.pk,),
            ),
            {"payment_status": RegistrationOrder.PaymentStatus.PAID, "_save": "Save"},
        )
        self.assertEqual(response.status_code, 403)
        self.unpaid_order.refresh_from_db()
        self.assertEqual(
            self.unpaid_order.payment_status,
            RegistrationOrder.PaymentStatus.PENDING,
        )

    def test_payment_attempts_require_finance_permission_and_are_read_only(self):
        attempt = self.paid_order.payment_attempts.get()
        staff = self.make_staff(
            "registration-no-finance",
            self.permission("view_paymentattempt", "paymentattempt"),
        )
        self.client.force_login(staff)
        response = self.client.get(
            reverse("admin:dic_paymentattempt_change", args=(attempt.pk,))
        )
        self.assertEqual(response.status_code, 403)

        staff.user_permissions.add(self.permission("can_view_dic_finance"))
        response = self.client.get(
            reverse("admin:dic_paymentattempt_change", args=(attempt.pk,))
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Provider-reported amount (NGN)")
        self.assertContains(response, "200.00")
        self.assertNotContains(response, "checkout.paystack.com")

        response = self.client.post(
            reverse("admin:dic_paymentattempt_change", args=(attempt.pk,)),
            {"status": PaymentAttempt.Status.FAILED, "_save": "Save"},
        )
        self.assertEqual(response.status_code, 403)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCESSFUL)

    def test_audit_events_are_immutable(self):
        event = DICAdminAuditEvent.objects.create(
            action="test_action",
            target_type="RegistrationOrder",
            target_id=str(self.paid_order.pk),
            details={"order_count": 1},
        )
        event.action = "changed"
        with self.assertRaisesMessage(
            ValidationError,
            "DIC administrative audit events are immutable.",
        ):
            event.save()
        with self.assertRaisesMessage(
            ValidationError,
            "DIC administrative audit events cannot be deleted.",
        ):
            event.delete()

    def test_staff_role_setup_creates_restricted_groups_idempotently(self):
        from django.contrib.auth.models import Group
        from django.core.management import call_command

        call_command("setup_dic_staff_roles")
        call_command("setup_dic_staff_roles")

        registration_staff = Group.objects.get(name="DIC Registration Staff")
        registration_codes = set(
            registration_staff.permissions.values_list("codename", flat=True)
        )
        self.assertIn("can_view_dic_operations", registration_codes)
        self.assertIn("can_export_dic_reports", registration_codes)
        self.assertNotIn("can_view_dic_finance", registration_codes)
        self.assertNotIn("view_paymentattempt", registration_codes)

        finance_reviewers = Group.objects.get(name="DIC Finance Reviewers")
        finance_codes = set(
            finance_reviewers.permissions.values_list("codename", flat=True)
        )
        self.assertIn("can_view_dic_finance", finance_codes)
        self.assertIn("view_paymentattempt", finance_codes)
        self.assertNotIn("can_export_dic_contact_information", finance_codes)

        administrators = Group.objects.get(name="DIC Administrators")
        self.assertTrue(
            administrators.permissions.filter(
                codename="can_manage_registration_access"
            ).exists()
        )
