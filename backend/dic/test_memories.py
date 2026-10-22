import io
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError, ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, RequestFactory, override_settings
from django.urls import reverse

from .memory_admin import CampPhotographAdmin, PhotographForm, MemoryActivityAdmin
from .memory_models import CampPhotograph, MemoryActivity
from .memory_storage import PrivateMemoryStorage, validate_photo
from .models import DICAdminAuditEvent
from .test_allocation import AllocationFixtures


def image_file():
    output = io.BytesIO()
    Image.new("RGB", (40, 30), "green").save(output, format="PNG", pnginfo=None)
    return SimpleUploadedFile("private-original.png", output.getvalue(), content_type="image/png")


class MemoryTests(AllocationFixtures, TransactionTestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.storage_settings = override_settings(DEBUG=True, DIC_MEMORY_STORAGE="local", DIC_MEMORY_LOCAL_ROOT=self.root.name)
        self.storage_settings.enable()
        self.addCleanup(self.storage_settings.disable)
        self.edition = self.make_edition()
        self.media = get_user_model().objects.create_user(username="media", is_staff=True)
        self.publisher = get_user_model().objects.create_user(username="publisher", is_staff=True)
        for codename in ("add_campphotograph", "change_campphotograph", "view_campphotograph"):
            permission = Permission.objects.get(codename=codename)
            self.media.user_permissions.add(permission)
            self.publisher.user_permissions.add(permission)
        self.publisher.user_permissions.add(Permission.objects.get(codename="publish_campphotograph"))
        self.admin = CampPhotographAdmin(CampPhotograph, AdminSite())

    def photo(self, **kwargs):
        return CampPhotograph.objects.create(edition=self.edition, photograph=image_file(), caption="Approved synthetic scene", alt_text="Synthetic green image", **kwargs)

    def request(self, user):
        request = RequestFactory().post("/admin/")
        request.user = user
        return request

    def publish(self, photo):
        self.admin.publish_selected(self.request(self.publisher), CampPhotograph.objects.filter(pk=photo.pk))
        photo.refresh_from_db()

    def test_drafts_and_review_are_private_even_with_known_id(self):
        for state in ("draft", "review"):
            photo = self.photo(state=state)
            self.assertEqual(self.client.get(reverse("dic:memory-image", args=[photo.pk])).status_code, 404)
            self.assertEqual(self.client.get(reverse("dic:memory-image", args=[photo.pk]) + "?preview=1").status_code, 404)
        self.assertEqual(self.client.get(reverse("dic:memories")).json(), {"photographs": []})

    def test_uploaders_cannot_publish_and_content_edits_withdraw_approval(self):
        photo = self.photo()
        with self.assertRaises(PermissionDenied):
            self.admin.publish_selected(self.request(self.media), CampPhotograph.objects.all())
        photo.state = "published"
        with self.assertRaises(PermissionDenied):
            photo.save(actor=self.media)
        photo.refresh_from_db()
        self.publish(photo)
        self.assertEqual(photo.published_by, self.publisher)
        self.assertIsNotNone(photo.published_at)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action="camp_photo_published").count(), 1)
        photo.caption = "Edited scene"
        photo.state = "review"
        self.admin.save_model(self.request(self.media), photo, None, True)
        self.assertIsNone(photo.published_at)
        self.assertEqual(self.client.get(reverse("dic:memory-image", args=[photo.pk])).status_code, 404)

    def test_admin_form_rejects_forged_published_state(self):
        form = PhotographForm(data={"edition": self.edition.pk, "caption": "Scene", "alt_text": "Scene", "state": "published", "display_order": 0}, files={"photograph": image_file()})
        self.assertFalse(form.is_valid())
        self.assertIn("state", form.errors)
        self.client.force_login(self.media)
        response = self.client.get(reverse("admin:dic_campphotograph_add"))
        self.assertEqual(response.status_code, 200)

    def test_media_admin_can_upload_draft_but_ordinary_staff_cannot(self):
        payload = {"edition": self.edition.pk, "caption": "Synthetic upload", "alt_text": "Synthetic image", "state": "review", "display_order": 3}
        self.client.force_login(self.media)
        response = self.client.post(reverse("admin:dic_campphotograph_add"), {**payload, "photograph": image_file(), "_save": "Save"})
        self.assertEqual(response.status_code, 302)
        photo = CampPhotograph.objects.get(caption="Synthetic upload")
        self.assertEqual(photo.state, "review")
        self.assertIsNone(photo.published_by)
        ordinary = get_user_model().objects.create_user(username="not-media", is_staff=True)
        self.client.force_login(ordinary)
        self.assertEqual(self.client.post(reverse("admin:dic_campphotograph_add"), {**payload, "photograph": image_file()}).status_code, 403)

    def test_public_filters_ordering_and_image_delivery(self):
        first = self.photo(display_order=2)
        featured = self.photo(featured=True, display_order=8)
        earlier = self.photo(display_order=1)
        tag = MemoryActivity.objects.create(name="Synthetic activity")
        first.activities.add(tag)
        self.publish(first)
        self.publish(featured)
        self.publish(earlier)
        data = self.client.get(reverse("dic:memories")).json()["photographs"]
        self.assertEqual([row["id"] for row in data], [featured.pk, earlier.pk, first.pk])
        self.assertNotIn("photograph", data[0])
        filtered = self.client.get(reverse("dic:memories"), {"edition": self.edition.pk, "activity": tag.pk}).json()["photographs"]
        self.assertEqual([row["id"] for row in filtered], [first.pk])
        other = self.photo()
        other.edition = self.make_edition(year=2097)
        other.save()
        other.activities.add(tag)
        self.publish(other)
        filtered = self.client.get(reverse("dic:memories"), {"edition": self.edition.pk, "activity": tag.pk}).json()["photographs"]
        self.assertEqual([row["id"] for row in filtered], [first.pk])
        self.assertEqual(self.client.get(reverse("dic:memories"), {"edition": "invalid"}).status_code, 400)
        response = self.client.get(reverse("dic:memory-image", args=[first.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertIn("no-store", response["Cache-Control"])
        response.close()
        self.admin.unpublish_selected(self.request(self.publisher), CampPhotograph.objects.filter(pk=first.pk))
        self.assertEqual(self.client.get(reverse("dic:memory-image", args=[first.pk])).status_code, 404)

    def test_private_preview_requires_staff_photo_permission(self):
        photo = self.photo()
        self.client.force_login(self.media)
        response = self.client.get(reverse("dic:memory-image", args=[photo.pk]) + "?preview=1")
        self.assertEqual(response.status_code, 200)
        response.close()
        ordinary = get_user_model().objects.create_user(username="ordinary", is_staff=True)
        self.client.force_login(ordinary)
        self.assertEqual(self.client.get(reverse("dic:memory-image", args=[photo.pk]) + "?preview=1").status_code, 404)

    def test_file_validation_and_local_storage_guard(self):
        with self.assertRaises(ValidationError):
            validate_photo(SimpleUploadedFile("fake.jpg", b"<script>invalid</script>"))
        large = image_file()
        large.size = 13 * 1024 * 1024
        with self.assertRaises(ValidationError):
            validate_photo(large)
        with override_settings(DEBUG=False, DIC_MEMORY_STORAGE="local"):
            with self.assertRaises(ImproperlyConfigured):
                PrivateMemoryStorage().save("photo", image_file())
        with override_settings(DEBUG=False, DIC_MEMORY_STORAGE="disabled"):
            form = PhotographForm(data={"edition": self.edition.pk, "caption": "Synthetic image", "alt_text": "Synthetic image", "state": "draft", "display_order": 0}, files={"photograph": image_file()})
            self.assertFalse(form.is_valid())
            self.assertIn("photograph", form.errors)

    def test_tag_edits_withdraw_published_content_for_review(self):
        tag = MemoryActivity.objects.create(name="Approved synthetic activity")
        photo = self.photo()
        photo.activities.add(tag)
        self.publish(photo)
        tag.name = "Edited synthetic activity"
        tag_admin = MemoryActivityAdmin(MemoryActivity, AdminSite())
        tag_admin.save_model(self.request(self.media), tag, SimpleNamespace(changed_data=["name"]), True)
        photo.refresh_from_db()
        self.assertEqual(photo.state, "review")
        self.assertIsNone(photo.published_at)
        self.assertEqual(self.client.get(reverse("dic:memories")).json()["photographs"], [])

    @override_settings(DIC_MEMORY_STORAGE="s3", DIC_MEMORY_S3_BUCKET="synthetic-private-bucket", DIC_MEMORY_S3_ENDPOINT="https://storage.example.invalid")
    def test_s3_private_integration_without_credentials(self):
        client = Mock()
        boto = SimpleNamespace(client=Mock(return_value=client))
        with patch.dict("sys.modules", {"boto3": boto}):
            storage = PrivateMemoryStorage()
            name = storage.save("original.png", image_file())
            payload = client.put_object.call_args.kwargs
            self.assertEqual(payload["Bucket"], "synthetic-private-bucket")
            self.assertNotIn("ACL", payload)
            self.assertTrue(name.endswith(".jpg"))
            normalized = Image.open(io.BytesIO(payload["Body"]))
            self.assertEqual(normalized.format, "JPEG")
            self.assertFalse(normalized.getexif())
            client.get_object.return_value = {"Body": io.BytesIO(payload["Body"])}
            self.assertTrue(storage.open(name).read())
            with self.assertRaises(ValueError):
                storage.url(name)
