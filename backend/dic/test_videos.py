import tempfile
from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.urls import reverse

from .memory_admin import MemoryActivityAdmin
from .memory_models import CampVideo, MemoryActivity
from .models import DICAdminAuditEvent
from .test_allocation import AllocationFixtures
from .test_memories import image_file
from .video_admin import CampVideoAdmin, VideoForm
from .video_providers import video_source


@override_settings(DIC_VIDEO_APPROVED_PROVIDERS=["youtube", "vimeo"])
class VideoTests(AllocationFixtures, TransactionTestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.storage_settings = override_settings(DEBUG=True, DIC_MEMORY_STORAGE="local", DIC_MEMORY_LOCAL_ROOT=self.root.name)
        self.storage_settings.enable()
        self.addCleanup(self.storage_settings.disable)
        self.edition = self.make_edition()
        self.media = get_user_model().objects.create_user(username="video-media", is_staff=True)
        self.publisher = get_user_model().objects.create_user(username="video-publisher", is_staff=True)
        for name in ("add_campvideo", "view_campvideo", "change_campvideo"):
            permission = Permission.objects.get(codename=name)
            self.media.user_permissions.add(permission)
            self.publisher.user_permissions.add(permission)
        self.publisher.user_permissions.add(Permission.objects.get(codename="publish_campvideo"))
        self.admin = CampVideoAdmin(CampVideo, admin.AdminSite())

    def video(self, **kwargs):
        defaults = dict(edition=self.edition, caption="Synthetic video", alt_text="Synthetic green thumbnail", video_url="https://www.youtube.com/watch?v=aaaaaaaaaaa", thumbnail=image_file())
        defaults.update(kwargs)
        return CampVideo.objects.create(**defaults)

    def request(self, user):
        request = RequestFactory().post("/admin/")
        request.user = user
        return request

    def publish(self, video):
        self.admin.publish_selected(self.request(self.publisher), CampVideo.objects.filter(pk=video.pk))
        video.refresh_from_db()

    def test_only_approved_provider_urls_produce_canonical_players(self):
        for url in ("https://youtu.be/aaaaaaaaaaa", "https://www.youtube.com/shorts/aaaaaaaaaaa", "https://www.youtube.com/watch?v=aaaaaaaaaaa&si=unused"):
            self.assertEqual(video_source(url), {"provider": "youtube", "embed_url": "https://www.youtube-nocookie.com/embed/aaaaaaaaaaa?playsinline=1"})
        self.assertEqual(video_source("https://vimeo.com/123456")["embed_url"], "https://player.vimeo.com/video/123456?dnt=1")
        for url in ("http://youtu.be/aaaaaaaaaaa", "javascript:alert(1)", "https://youtube.com.evil.invalid/watch?v=aaaaaaaaaaa", "https://youtube.com@evil.invalid/watch?v=aaaaaaaaaaa", "https://user:secret@youtube.com/watch?v=aaaaaaaaaaa", "https://youtube.com:443/watch?v=aaaaaaaaaaa", "https://youtube.com/watch?v=aaaaaaaaaaa&v=bbbbbbbbbbb", "https://youtube.com/watch?v=aaaaaaaaaaa&v=", "https://youtube.com/embed/<script>", "https://youtube.com/watch?v=short", "https://vimeo.com/not-a-video", "https://youtu.be/aaaaaaaaaaa#fragment", "https://you\ntube.com/watch?v=aaaaaaaaaaa", "https://example.invalid/file.mp4"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                video_source(url)
        with override_settings(DIC_VIDEO_APPROVED_PROVIDERS=[]):
            with self.assertRaises(ValidationError):
                self.video()

    def test_drafts_and_review_hide_links_thumbnails_and_playback(self):
        for state in ("draft", "review"):
            video = self.video(state=state)
            for name in ("video-playback", "video-thumbnail"):
                self.assertEqual(self.client.get(reverse("dic:" + name, args=[video.pk])).status_code, 404)
            self.assertEqual(self.client.get(reverse("dic:video-thumbnail", args=[video.pk]) + "?preview=1").status_code, 404)
        self.assertEqual(self.client.get(reverse("dic:videos")).json(), {"videos": []})

    def test_publication_permission_and_audit_and_edit_withdrawal(self):
        video = self.video()
        with self.assertRaises(PermissionDenied):
            self.admin.publish_selected(self.request(self.media), CampVideo.objects.all())
        video.state = "published"
        with self.assertRaises(PermissionDenied):
            video.save(actor=self.media)
        video.refresh_from_db()
        self.publish(video)
        self.assertEqual(video.published_by, self.publisher)
        self.assertIsNotNone(video.published_at)
        self.assertTrue(DICAdminAuditEvent.objects.filter(action="camp_video_published", actor=self.publisher).exists())
        video.caption = "Edited synthetic recording"
        video.state = "review"
        self.admin.save_model(self.request(self.media), video, None, True)
        self.assertIsNone(video.published_at)
        self.assertEqual(self.client.get(reverse("dic:video-playback", args=[video.pk])).status_code, 404)

    def test_provider_revocation_hides_published_content_and_allows_withdrawal(self):
        video = self.video()
        self.publish(video)
        with override_settings(DIC_VIDEO_APPROVED_PROVIDERS=[]):
            self.assertEqual(self.client.get(reverse("dic:videos")).json(), {"videos": []})
            for name in ("video-playback", "video-thumbnail"):
                self.assertEqual(self.client.get(reverse("dic:" + name, args=[video.pk])).status_code, 404)
            self.admin.unpublish_selected(self.request(self.publisher), CampVideo.objects.all())
        video.refresh_from_db()
        self.assertEqual(video.state, "draft")
        self.assertIsNone(video.published_at)

    def test_filters_ordering_and_lazy_playback_contract(self):
        first = self.video(display_order=2)
        earlier = self.video(display_order=1)
        featured = self.video(featured=True, display_order=9, video_url="https://vimeo.com/123456")
        other = self.video(edition=self.make_edition(year=2097))
        tag = MemoryActivity.objects.create(name="Synthetic approved activity")
        first.activities.add(tag)
        other.activities.add(tag)
        for video in (first, earlier, featured, other):
            self.publish(video)
        data = self.client.get(reverse("dic:videos"), {"edition": self.edition.pk}).json()["videos"]
        self.assertEqual([row["id"] for row in data], [featured.pk, earlier.pk, first.pk])
        self.assertTrue(all("video_url" not in row and "embed_url" not in row and "thumbnail" not in row for row in data))
        self.assertEqual(self.client.get(reverse("dic:videos"), {"edition": self.edition.pk, "activity": tag.pk}).json()["videos"][0]["id"], first.pk)
        self.assertEqual(self.client.get(reverse("dic:videos"), {"edition": "invalid"}).status_code, 400)
        response = self.client.get(reverse("dic:video-playback", args=[featured.pk]))
        self.assertEqual(response.json()["embed_url"], "https://player.vimeo.com/video/123456?dnt=1")
        self.assertIn("no-store", response["Cache-Control"])
        image = self.client.get(reverse("dic:video-thumbnail", args=[featured.pk]))
        self.assertEqual(image["Content-Type"], "image/jpeg")
        self.assertIn("no-store", image["Cache-Control"])
        image.close()

    def test_admin_upload_permissions_and_forged_publish_state(self):
        payload = dict(edition=self.edition.pk, video_url="https://youtu.be/aaaaaaaaaaa", caption="Synthetic upload", alt_text="Synthetic thumbnail", display_order=0, state="review")
        form = VideoForm(data={**payload, "state": "published"}, files={"thumbnail": image_file()})
        self.assertFalse(form.is_valid())
        self.assertIn("state", form.errors)
        self.client.force_login(self.media)
        self.assertEqual(self.client.post(reverse("admin:dic_campvideo_add"), {**payload, "thumbnail": image_file(), "_save": "Save"}).status_code, 302)
        video = CampVideo.objects.get(caption="Synthetic upload")
        response = self.client.get(reverse("dic:video-thumbnail", args=[video.pk]) + "?preview=1")
        self.assertEqual(response.status_code, 200)
        response.close()
        ordinary = get_user_model().objects.create_user(username="ordinary-staff", is_staff=True)
        self.client.force_login(ordinary)
        self.assertEqual(self.client.post(reverse("admin:dic_campvideo_add"), {**payload, "thumbnail": image_file()}).status_code, 403)
        self.assertEqual(self.client.get(reverse("dic:video-thumbnail", args=[video.pk]) + "?preview=1").status_code, 404)

    def test_tag_edits_withdraw_video_and_invalid_files_are_rejected(self):
        tag = MemoryActivity.objects.create(name="Synthetic category")
        video = self.video()
        video.activities.add(tag)
        self.publish(video)
        tag.name = "Changed synthetic category"
        MemoryActivityAdmin(MemoryActivity, admin.AdminSite()).save_model(self.request(self.media), tag, SimpleNamespace(changed_data=["name"]), True)
        video.refresh_from_db()
        self.assertEqual(video.state, "review")
        self.assertIsNone(video.published_at)
        from django.core.files.uploadedfile import SimpleUploadedFile
        with self.assertRaises(ValidationError):
            self.video(thumbnail=SimpleUploadedFile("fake.png", b"not an image"))
