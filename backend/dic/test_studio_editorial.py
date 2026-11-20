"""Media Studio publication and visibility regression tests (synthetic only)."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .studio_models import StudioAsset
from .studio_publication_models import StudioCollection, StudioPublication


class StudioEditorialTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser(
            'editorial-owner', 'editorial-owner@example.test', 'synthetic')
        self.staff = Client()
        self.staff.force_login(self.owner)
        self.anonymous = Client()

    def get_public(self, **params):
        return self.anonymous.get(reverse('dic:studio-public-editorial'), params)

    def create_collection(self, name='Weekly Qur’an Lessons', slug='weekly-quran-lessons',
                          kind='programme'):
        result = self.staff.post(reverse('dic:studio-editorial-collections'), {
            'title': name, 'slug': slug, 'kind': kind,
        }, content_type='application/json')
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()['collection']['id']

    def create_article(self, collection_id=None):
        body = {'kind': 'article', 'title': 'Synthetic reflection', 'body': 'Text only'}
        if collection_id:
            body['collection_id'] = collection_id
        result = self.staff.post(reverse('dic:studio-editorial-items'),
                                 body, content_type='application/json')
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()['item']['id']

    def action(self, item_id, action):
        return self.staff.post(reverse('dic:studio-editorial-item-detail',
                                       args=[item_id]), {'action': action},
                               content_type='application/json')

    def test_only_published_items_in_visible_collections_appear_publicly(self):
        group = self.create_collection()
        item_id = self.create_article(group)
        self.assertEqual(self.get_public().json()['items'], [])
        self.assertEqual(self.action(item_id, 'publish').status_code, 200)
        self.assertEqual(self.get_public().json()['items'], [])
        result = self.staff.patch(reverse('dic:studio-editorial-collection-detail',
                                          args=[group]), {'is_public': True},
                                  content_type='application/json')
        self.assertEqual(result.status_code, 200, result.content)
        public = self.get_public().json()
        self.assertEqual(len(public['items']), 1)
        self.assertEqual(public['items'][0]['body'], 'Text only')
        self.assertEqual(public['collections'][0]['slug'], 'weekly-quran-lessons')
        self.assertEqual(self.action(item_id, 'withdraw').status_code, 200)
        self.assertEqual(self.get_public().json()['items'], [])

    def test_public_cannot_enumerate_draft_pdf_and_rejects_invalid_files(self):
        item_id = self.create_article()
        self.assertEqual(self.anonymous.get(reverse('dic:studio-public-editorial-document',
                                                   args=[item_id])).status_code, 404)
        upload = SimpleUploadedFile('suspicious.pdf', b'NOT-A-PDF',
                                     content_type='application/pdf')
        result = self.staff.post(reverse('dic:studio-editorial-items'), {
            'kind': 'document', 'title': 'Synthetic document', 'document': upload,
        })
        self.assertEqual(result.status_code, 400)
        self.assertEqual(StudioPublication.objects.count(), 1)

    def test_nonstaff_denied_edits_while_public_metadata_remains_anonymous(self):
        response = self.anonymous.get(reverse('dic:studio-editorial-items'))
        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(self.get_public().status_code, 200)

    def test_provider_and_meet_links_are_checked_before_publication(self):
        response = self.staff.post(reverse('dic:studio-editorial-items'), {
            'kind': 'live', 'title': 'Synthetic live', 'meeting_url': 'https://evil.example/meet',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        response = self.staff.post(reverse('dic:studio-editorial-items'), {
            'kind': 'live', 'title': 'Synthetic Google Meet',
            'meeting_url': 'https://meet.google.com/abc-defg-hij',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        with patch('dic.studio_editorial_api.notify_publication', return_value='unconfigured'):
            result = self.action(response.json()['item']['id'], 'publish')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.get_public().json()['items'][0]['meeting_url'],
                         'https://meet.google.com/abc-defg-hij')

    def test_collection_cannot_override_fixed_media_categories(self):
        result = self.staff.post(reverse('dic:studio-editorial-collections'), {
            'title': 'Fake All Videos', 'slug': 'videos',
        }, content_type='application/json')
        self.assertEqual(result.status_code, 400)
        self.assertEqual(StudioCollection.objects.count(), 0)

    def test_homepage_media_stays_capped_independent_of_editorial_publications(self):
        self.create_article()
        self.assertEqual(StudioAsset.objects.count(), 0)
        self.assertEqual(self.anonymous.get(reverse('dic:studio-public-placements'),
                                           {'destination': 'foundation_home'}).json()['items'], [])


    def test_draft_delete_is_audited_and_never_deletes_published_history(self):
        from .models import DICAdminAuditEvent
        draft_id = self.create_article()
        path = reverse('dic:studio-editorial-item-detail', args=[draft_id])
        deleted = self.staff.delete(path)
        self.assertEqual(deleted.status_code, 200, deleted.content)
        self.assertFalse(StudioPublication.objects.filter(pk=draft_id).exists())
        self.assertTrue(DICAdminAuditEvent.objects.filter(
            target_type='StudioPublication', target_id=str(draft_id),
            action='studio_publication_draft_deleted').exists())
        item_id = self.create_article()
        with patch('dic.studio_editorial_api.notify_publication', return_value='unconfigured'):
            self.assertEqual(self.action(item_id, 'publish').status_code, 200)
        published_path = reverse('dic:studio-editorial-item-detail', args=[item_id])
        self.assertEqual(self.staff.delete(published_path).status_code, 400)
        self.assertEqual(self.action(item_id, 'withdraw').status_code, 200)
        self.assertEqual(self.staff.delete(published_path).status_code, 400)
        self.assertTrue(StudioPublication.objects.filter(pk=item_id).exists())
        self.assertEqual(self.anonymous.delete(published_path).status_code, 403)



    def test_annual_itinerary_only_published_approved_events_by_lagos_year(self):
        from unittest.mock import patch
        url = reverse('dic:studio-public-itinerary')
        data = {
            'kind': 'event', 'title': 'Synthetic annual seminar',
            'description': 'Official schedule test', 'event_venue': 'Lagos',
            'event_at': '2026-12-31T23:30:00+00:00',
            'event_end_at': '2027-01-01T00:00:00+00:00',
            'event_status': 'scheduled',
        }
        created = self.staff.post(reverse('dic:studio-editorial-items'),
                                  data, content_type='application/json')
        self.assertEqual(created.status_code, 201, created.content)
        item = created.json()['item']['id']
        self.assertEqual(self.anonymous.get(url, {'year': 2027}).json()['items'], [])
        with patch('dic.studio_editorial_api.notify_publication', return_value='unconfigured'):
            self.assertEqual(self.action(item, 'publish').status_code, 200)
        result = self.anonymous.get(url, {'year': 2027})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(len(result.json()['items']), 1)
        self.assertEqual(result.json()['items'][0]['event_venue'], 'Lagos')
        self.assertEqual(self.anonymous.get(url, {'year': 2026}).json()['items'], [])
        self.assertEqual(self.action(item, 'withdraw').status_code, 200)
        self.assertEqual(self.anonymous.get(url, {'year': 2027}).json()['items'], [])
        self.assertEqual(self.anonymous.get(url, {'year': '2027x'}).status_code, 400)

    def test_itinerary_rejects_bad_ranges_missing_dates_and_unapproved_edits(self):
        url = reverse('dic:studio-editorial-items')
        row = {'kind': 'event', 'title': 'Synthetic camp event',
               'event_at': '2026-12-24T09:00:00+01:00',
               'event_end_at': '2026-12-23T12:00:00+01:00'}
        result = self.staff.post(url, row, content_type='application/json')
        self.assertEqual(result.status_code, 400)
        row['event_end_at'] = '2026-12-24T11:00:00+01:00'
        valid = self.staff.post(url, row, content_type='application/json')
        self.assertEqual(valid.status_code, 201, valid.content)
        item = valid.json()['item']['id']
        with patch('dic.studio_editorial_api.notify_publication', return_value='unconfigured'):
            self.assertEqual(self.action(item, 'publish').status_code, 200)
        path = reverse('dic:studio-editorial-item-detail', args=[item])
        self.assertEqual(self.staff.patch(path, {'event_venue': 'Unexpected'},
                                          content_type='application/json').status_code, 400)
        self.assertEqual(self.anonymous.get(reverse('dic:studio-editorial-items')).status_code in (401,403), True)
