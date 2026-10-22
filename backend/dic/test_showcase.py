import tempfile
from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TransactionTestCase, RequestFactory, override_settings
from django.urls import reverse
from django.contrib.messages.storage.fallback import FallbackStorage

from .showcase_models import Lecturer, LecturerAppearance, CampActivity
from .showcase_admin import LecturerAdmin, LecturerAppearanceAdmin, CampActivityAdmin
from .test_allocation import AllocationFixtures
from .test_memories import image_file
from .models import DICAdminAuditEvent


class ShowcaseTests(AllocationFixtures, TransactionTestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        override = override_settings(DEBUG=True, DIC_MEMORY_STORAGE="local", DIC_MEMORY_LOCAL_ROOT=self.root.name)
        override.enable()
        self.addCleanup(override.disable)
        self.edition = self.make_edition(year=2026)
        self.previous = self.make_edition(year=2025)
        self.media = get_user_model().objects.create_user(username="showcase-editor", is_staff=True)
        self.publisher = get_user_model().objects.create_user(username="showcase-publisher", is_staff=True)
        self.verifier = get_user_model().objects.create_user(username="showcase-verifier", is_staff=True)
        for model in ("lecturer", "lecturerappearance", "campactivity"):
            for action in ("add", "view", "change"):
                permission = Permission.objects.get(codename=f"{action}_{model}")
                for user in (self.media, self.publisher, self.verifier):
                    user.user_permissions.add(permission)
        for model in ("lecturerappearance", "campactivity"):
            self.publisher.user_permissions.add(Permission.objects.get(codename=f"publish_{model}"))
        self.verifier.user_permissions.add(Permission.objects.get(codename="verify_lecturerappearance"))
        self.lecturer = Lecturer.objects.create(name="Synthetic Lecturer", photograph=image_file(), alt_text="Synthetic green portrait", biography="Synthetic biography for testing only.", designation="Synthetic designation")
        self.appearance_admin = LecturerAppearanceAdmin(LecturerAppearance, admin.AdminSite())
        self.activity_admin = CampActivityAdmin(CampActivity, admin.AdminSite())

    def request(self, user):
        request = RequestFactory().post("/admin/")
        request.user = user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def appearance(self, **kwargs):
        fields = dict(lecturer=self.lecturer, edition=self.edition, participation_type="upcoming", topic="Synthetic approved topic")
        fields.update(kwargs)
        return LecturerAppearance.objects.create(**fields)

    def publish(self, obj):
        model_admin = self.appearance_admin if isinstance(obj, LecturerAppearance) else self.activity_admin
        model_admin.publish_selected(self.request(self.publisher), type(obj).objects.filter(pk=obj.pk))
        obj.refresh_from_db()

    def verify(self, obj):
        obj.verification_note = "Synthetic committee evidence, not a real invitation."
        obj.state = "review"
        obj.save(actor=self.media)
        self.appearance_admin.verify_selected(self.request(self.verifier), LecturerAppearance.objects.filter(pk=obj.pk))
        obj.refresh_from_db()

    def activity(self, **kwargs):
        fields = dict(edition=self.edition, title="Synthetic activity", description="Synthetic approved description.", category="Synthetic category")
        fields.update(kwargs)
        return CampActivity.objects.create(**fields)

    def test_draft_and_review_privacy_and_authenticated_previews(self):
        appearance = self.appearance(state="review")
        activity = self.activity(photograph=image_file(), alt_text="Synthetic activity image")
        self.assertEqual(self.client.get(reverse("dic:showcase")).json(), {"upcoming": [], "previous": [], "activities": []})
        for kind, pk in (("lecturer", appearance.pk), ("activity", activity.pk), ("identity", self.lecturer.pk)):
            url = reverse("dic:showcase-image", args=[kind, pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.get(url + "?preview=1").status_code, 404)
        self.client.force_login(self.media)
        for kind, pk in (("lecturer", appearance.pk), ("activity", activity.pk), ("identity", self.lecturer.pk)):
            response = self.client.get(reverse("dic:showcase-image", args=[kind, pk]) + "?preview=1")
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"])
            response.close()

    def test_publish_and_verification_are_distinct_permissions(self):
        appearance = self.appearance()
        with self.assertRaises(PermissionDenied):
            self.appearance_admin.publish_selected(self.request(self.media), LecturerAppearance.objects.all())
        with self.assertRaises(PermissionDenied):
            self.appearance_admin.verify_selected(self.request(self.publisher), LecturerAppearance.objects.all())
        appearance.confirmation_status = "confirmed"
        appearance.verification_note = "Synthetic evidence"
        with self.assertRaises(PermissionDenied):
            appearance.save(actor=self.publisher)
        appearance.refresh_from_db()
        self.publish(appearance)
        public = self.client.get(reverse("dic:showcase")).json()["upcoming"][0]
        self.assertFalse(public["confirmed"])
        self.assertNotIn("verification_note", public)
        self.verify(appearance)
        self.assertEqual(appearance.state, "review")
        self.assertTrue(appearance.verified)
        self.assertEqual(appearance.verified_by, self.verifier)
        self.publish(appearance)
        self.assertTrue(self.client.get(reverse("dic:showcase")).json()["upcoming"][0]["confirmed"])
        self.assertTrue(DICAdminAuditEvent.objects.filter(action="lecturer_participation_verified").exists())
        self.assertTrue(DICAdminAuditEvent.objects.filter(action="showcase_published").exists())

    def test_verification_needs_evidence_and_forged_form_states_rejected(self):
        obj = self.appearance()
        self.appearance_admin.verify_selected(self.request(self.verifier), LecturerAppearance.objects.all())
        obj.refresh_from_db()
        self.assertFalse(obj.verified)
        form_class = self.appearance_admin.get_form(self.request(self.media), obj)
        form = form_class(data={"lecturer": self.lecturer.pk, "edition": self.edition.pk, "participation_type": "upcoming", "topic": "Synthetic", "state": "published", "confirmation_status": "confirmed", "display_order": 0})
        self.assertFalse(form.is_valid())
        self.assertIn("state", form.errors)
        self.assertIn("confirmation_status", form.errors)

    def test_shared_identity_edit_withdraws_all_editions_and_confirmation(self):
        upcoming = self.appearance()
        old = self.appearance(edition=self.previous, participation_type="previous")
        for obj in (upcoming, old):
            self.verify(obj)
            self.publish(obj)
        self.assertEqual(Lecturer.objects.count(), 1)
        self.lecturer.biography = "Edited synthetic biography."
        LecturerAdmin(Lecturer, admin.AdminSite()).save_model(self.request(self.media), self.lecturer, SimpleNamespace(changed_data=["biography"]), True)
        for obj in (upcoming, old):
            obj.refresh_from_db()
            self.assertEqual(obj.state, "review")
            self.assertFalse(obj.verified)
        self.assertEqual(self.client.get(reverse("dic:showcase")).json()["upcoming"], [])

    def test_previous_topics_require_verified_evidence_and_edition_filter(self):
        old = self.appearance(edition=self.previous, participation_type="previous")
        self.publish(old)
        self.assertEqual(self.client.get(reverse("dic:showcase")).json()["previous"][0]["topic"], "")
        self.verify(old)
        self.publish(old)
        data = self.client.get(reverse("dic:showcase"), {"edition": self.previous.pk}).json()
        self.assertEqual(data["previous"][0]["topic"], old.topic)
        self.assertEqual(self.client.get(reverse("dic:showcase"), {"edition": self.edition.pk}).json()["previous"], [])
        self.assertEqual(self.client.get(reverse("dic:showcase"), {"edition": "bad"}).status_code, 400)

    def test_activity_publication_ordering_edition_and_optional_image(self):
        first = self.activity(display_order=2)
        earlier = self.activity(title="Synthetic earlier", display_order=1)
        featured = self.activity(title="Synthetic featured", featured=True, display_order=9, photograph=image_file(), alt_text="Synthetic illustration")
        other = self.activity(edition=self.previous)
        with self.assertRaises(PermissionDenied):
            self.activity_admin.publish_selected(self.request(self.media), CampActivity.objects.all())
        for obj in (first, earlier, featured, other):
            self.publish(obj)
        data = self.client.get(reverse("dic:showcase")).json()["activities"]
        self.assertEqual([item["id"] for item in data], [featured.pk, earlier.pk, first.pk])
        self.assertIsNone(data[1]["image_url"])
        response = self.client.get(reverse("dic:showcase-image", args=["activity", featured.pk]))
        self.assertEqual(response["Content-Type"], "image/jpeg")
        response.close()
        self.activity_admin.withdraw_selected(self.request(self.publisher), CampActivity.objects.filter(pk=featured.pk))
        self.assertEqual(self.client.get(reverse("dic:showcase-image", args=["activity", featured.pk])).status_code, 404)

    def test_edit_activity_returns_to_review_and_requires_alt_text(self):
        obj = self.activity()
        self.publish(obj)
        obj.description = "Edited synthetic description"
        obj.state = "review"
        self.activity_admin.save_model(self.request(self.media), obj, None, True)
        self.assertIsNone(obj.published_at)
        with self.assertRaises(ValidationError):
            self.activity(photograph=image_file()).full_clean()

    def test_declined_not_published_and_unverified_database_flag_fails_closed(self):
        obj = self.appearance(confirmation_status="declined")
        self.publish(obj)
        self.assertNotEqual(obj.state, "published")
        obj.confirmation_status = "pending"
        obj.save()
        self.publish(obj)
        LecturerAppearance.objects.filter(pk=obj.pk).update(confirmation_status="confirmed", verified_by=None, verified_at=None)
        self.assertFalse(self.client.get(reverse("dic:showcase")).json()["upcoming"][0]["confirmed"])

    def test_admin_pages_and_upload_permission(self):
        self.client.force_login(self.media)
        for model in ("lecturer", "lecturerappearance", "campactivity"):
            self.assertEqual(self.client.get(reverse(f"admin:dic_{model}_add")).status_code, 200)
        ordinary = get_user_model().objects.create_user(username="unprivileged", is_staff=True)
        self.client.force_login(ordinary)
        self.assertEqual(self.client.get(reverse("admin:dic_lecturer_add")).status_code, 403)

    def test_admin_identity_upload_and_invalid_images(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.media)
        payload = {"name": "Synthetic second identity", "alt_text": "Synthetic portrait", "biography": "Synthetic biography", "designation": "Synthetic designation", "_save": "Save"}
        invalid = self.client.post(reverse("admin:dic_lecturer_add"), {**payload, "photograph": SimpleUploadedFile("fake.jpg", b"not an image")})
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(Lecturer.objects.filter(name=payload["name"]).exists())
        valid = self.client.post(reverse("admin:dic_lecturer_add"), {**payload, "photograph": image_file()})
        self.assertEqual(valid.status_code, 302)
        self.assertTrue(Lecturer.objects.filter(name=payload["name"]).exists())
        self.assertTrue(DICAdminAuditEvent.objects.filter(action="lecturer_identity_created", actor=self.media).exists())

    def test_active_superuser_can_verify_and_publish_without_conflating_actions(self):
        root = get_user_model().objects.create_superuser(username="synthetic-superuser", email="synthetic@example.invalid", password="synthetic-only-test-password")
        obj = self.appearance(verification_note="Synthetic evidence for authorized review")
        self.appearance_admin.verify_selected(self.request(root), LecturerAppearance.objects.filter(pk=obj.pk))
        obj.refresh_from_db()
        self.assertTrue(obj.verified)
        self.assertEqual(obj.state, "review")
        self.appearance_admin.publish_selected(self.request(root), LecturerAppearance.objects.filter(pk=obj.pk))
        obj.refresh_from_db()
        self.assertEqual(obj.state, "published")
