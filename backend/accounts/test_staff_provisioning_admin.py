"""Admin-only, opt-in production provisioning acceptance. Synthetic database only."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from dic.management.commands.provision_dawana_staff_accounts import ACCOUNTS


class StaffProvisioningAdminTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.owner = self.User.objects.create_superuser(
            username="synthetic-owner", password="Synthetic-Owner-Strong-927!"
        )
        self.url = reverse("admin:accounts_user_provision_dawana_staff")
        self.client.force_login(self.owner)

    def test_preview_and_invalid_confirmation_do_not_modify_database(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PROVISION 8 STAFF ACCOUNTS")
        self.assertContains(response, "Dawana_Media_003")
        self.assertEqual(Group.objects.count(), 0)
        response = self.client.post(self.url, {"confirmation": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Group.objects.count(), 0)
        self.assertEqual(self.User.objects.count(), 1)

    def test_non_owner_staff_cannot_preview_or_provision(self):
        other = self.User.objects.create_user(
            username="non-owner-staff", password="Synthetic-Operator-Strong-927!",
            is_staff=True, is_active=True
        )
        # Give access to the user changelist but not to the owner-only action.
        from django.contrib.auth.models import Permission
        other.user_permissions.add(Permission.objects.get(
            content_type__app_label="accounts", codename="view_user"
        ))
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(
            self.client.post(self.url, {"confirmation": "PROVISION 8 STAFF ACCOUNTS"}).status_code, 403
        )
        self.assertFalse(self.User.objects.filter(username="Operations_1").exists())

    def test_owner_post_creates_only_dormant_accounts_and_audit(self):
        response = self.client.post(self.url, {"confirmation": "PROVISION 8 STAFF ACCOUNTS"})
        self.assertRedirects(response, reverse("admin:accounts_user_changelist"))
        from dic.models import DICAdminAuditEvent
        for username, label, group_name in ACCOUNTS:
            user = self.User.objects.get(username=username)
            self.assertFalse(user.is_active)
            self.assertTrue(user.is_staff)
            self.assertFalse(user.is_superuser)
            self.assertFalse(user.has_usable_password())
            self.assertEqual(set(user.groups.values_list("name", flat=True)), {group_name})
            if label:
                self.assertEqual(user.first_name, label)
        self.assertEqual(DICAdminAuditEvent.objects.filter(
            action="staff_account_prepared", actor=self.owner
        ).count(), 8)
        self.assertEqual(self.User.objects.filter(is_superuser=True).count(), 1)
        self.assertEqual(self.User.objects.count(), 9)

    def test_missing_recording_permission_metadata_is_surgically_recovered(self):
        from django.contrib.contenttypes.models import ContentType
        from django.contrib.auth.models import Permission
        from dic.models import DICAdminAuditEvent
        from dic.camp_release_models import LectureRecording

        # Reproduce the live DB condition: the 0042 table exists but
        # post_migrate did not create this model's ContentType or permissions.
        ContentType.objects.filter(app_label="dic", model="lecturerecording").delete()
        self.assertFalse(ContentType.objects.filter(
            app_label="dic", model="lecturerecording"
        ).exists())

        response = self.client.post(
            self.url, {"confirmation": "PROVISION 8 STAFF ACCOUNTS"}
        )
        self.assertRedirects(response, reverse("admin:accounts_user_changelist"))
        ct = ContentType.objects.get(app_label="dic", model="lecturerecording")
        expected = {
            "view_lecturerecording", "add_lecturerecording",
            "change_lecturerecording", "publish_lecturerecording",
        }
        self.assertEqual(
            set(Permission.objects.filter(content_type=ct).values_list(
                "codename", flat=True
            )), expected
        )
        self.assertEqual(
            DICAdminAuditEvent.objects.filter(
                action="staff_permission_metadata_repaired", actor=self.owner
            ).count(), 1
        )
        media = self.User.objects.get(username="Dawana_Media_003")
        self.assertFalse(media.is_active)
        self.assertFalse(media.has_usable_password())
        self.assertEqual(
            set(media.groups.first().permissions.filter(
                codename__in=expected
            ).values_list("codename", flat=True)), expected
        )

    def test_colliding_username_rolls_back_permission_metadata_repair(self):
        from django.contrib.contenttypes.models import ContentType
        ContentType.objects.filter(app_label="dic", model="lecturerecording").delete()
        self.User.objects.create_user(username="Operations_2")
        response = self.client.post(
            self.url, {"confirmation": "PROVISION 8 STAFF ACCOUNTS"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContentType.objects.filter(
            app_label="dic", model="lecturerecording"
        ).exists())
        self.assertFalse(self.User.objects.filter(username="Operations_1").exists())

    def test_collision_fails_closed_without_creating_groups_or_users(self):
        existing = self.User.objects.create_user(username="Operations_3")
        response = self.client.post(self.url, {"confirmation": "PROVISION 8 STAFF ACCOUNTS"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Group.objects.count(), 0)
        self.assertEqual(self.User.objects.count(), 2)
        existing.refresh_from_db()
        self.assertTrue(existing.is_active)

    def test_csrf_is_required_for_post(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        response = browser.post(self.url, {"confirmation": "PROVISION 8 STAFF ACCOUNTS"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.User.objects.filter(username="Operations_1").exists())
