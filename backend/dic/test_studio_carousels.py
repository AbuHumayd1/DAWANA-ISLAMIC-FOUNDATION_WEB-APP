"""Acceptance guards for grouped Studio publications."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.urls import reverse
from .studio_carousel_models import StudioCarousel, validate_carousel_audio


class CarouselPublishingTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser(
            username='carousel-owner', email='carousel@example.test', password='not-a-production-secret')
        self.staff_url = reverse('dic:studio-carousels')
        self.public_url = reverse('dic:studio-public-carousels')

    def test_public_feed_has_no_unpublished_carousels(self):
        StudioCarousel.objects.create(title='Pending materials', format='images', created_by=self.owner)
        response = self.client.get(self.public_url, {'destination': 'dic_memories'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'], [])

    def test_anonymous_cannot_create_carousel(self):
        response = self.client.post(self.staff_url, {'title': 'New story', 'format': 'images'},
                                    content_type='application/json')
        self.assertIn(response.status_code, (401, 403))

    def test_draft_creation_does_not_publish_media(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.staff_url,
                                    data='{"title": "Eight learning cards", "format": "images"}',
                                    content_type='application/json')
        self.assertEqual(response.status_code, 201)
        record = StudioCarousel.objects.get(pk=response.json()['carousel']['id'])
        self.assertEqual(record.state, 'draft')
        self.assertFalse(record.placements.exists())

    def test_cannot_publish_empty_carousel(self):
        self.client.force_login(self.owner)
        carousel = StudioCarousel.objects.create(title='Incomplete', format='images', created_by=self.owner)
        response = self.client.post(
            reverse('dic:studio-carousel-detail', args=[carousel.pk]),
            data='{"action":"publish","destinations":[{"destination":"foundation_home"}]}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        carousel.refresh_from_db()
        self.assertEqual(carousel.state, 'draft')

    def test_public_rejects_private_destination(self):
        self.assertEqual(self.client.get(self.public_url, {'destination': 'camper_resources'}).status_code, 400)

    def test_publisher_deletion_is_recoverable_and_audited(self):
        from .models import DICAdminAuditEvent
        self.client.force_login(self.owner)
        carousel = StudioCarousel.objects.create(title='Withdraw me', format='mixed', created_by=self.owner)
        response = self.client.post(reverse('dic:studio-carousel-detail', args=[carousel.pk]),
            data='{"action":"delete"}', content_type='application/json')
        self.assertEqual(response.status_code, 200)
        carousel.refresh_from_db()
        self.assertIsNotNone(carousel.deleted_at)
        self.assertFalse(carousel.placements.exists())
        self.assertTrue(DICAdminAuditEvent.objects.filter(
            target_type='StudioCarousel', target_id=str(carousel.pk),
            action='studio_carousel_delete').exists())

    def test_rejects_disguised_soundtrack(self):
        disguised = SimpleUploadedFile('track.mp3', b'not actually an mp3 file')
        with self.assertRaises(ValidationError):
            validate_carousel_audio(disguised)

    def test_rejects_invalid_carousel_format(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.staff_url,
            data='{"title":"Invalid","format":"slideshow"}', content_type='application/json')
        self.assertEqual(response.status_code, 400)
