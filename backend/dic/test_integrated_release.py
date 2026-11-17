"""Integrated release acceptance on disposable PostgreSQL."""
import hashlib,io,json,tempfile
from datetime import date,datetime,time,timedelta,timezone as utc
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase,override_settings,Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from . import test_participant_portal as portal
from .models import TimetableEntry,House,CertificateRelease,ParticipationCertificate,LectureRecording,DICAdminAuditEvent
from .management.commands.initialize_dic2026_release import initialize,SOURCE
from .timetable_services import publish_days


@override_settings(**portal.TEST_DELIVERY)
class IntegratedReleaseTests(portal.PortalFixtures,TestCase):
    def setUp(self):
        super().setUp()
        self.owner=get_user_model().objects.create_superuser('release-owner','owner@example.test','synthetic')
        self.edition.year=2026;self.edition.camp_start_date=date(2026,12,23);self.edition.camp_end_date=date(2027,1,1)
        self.edition.save(update_fields=['year','camp_start_date','camp_end_date'])

    def test_reference_initialization_idempotent_preserves_edits_and_assignments(self):
        count=initialize(self.edition,self.owner)
        self.assertGreater(count,170);self.assertEqual(House.objects.filter(edition=self.edition).count(),8)
        self.assertTrue(all(h.capacity == 30 and h.badge_colour for h in House.objects.filter(edition=self.edition)))
        self.edition.refresh_from_db()
        self.assertEqual(self.edition.housing_age_reference_date, date(2026, 12, 23))
        self.assertEqual(TimetableEntry.objects.filter(timetable_type='food').count(),27)
        row=TimetableEntry.objects.filter(timetable_type='food').first();row.description='Administrator edit';row.save()
        self.assertEqual(initialize(self.edition,self.owner),0)
        row.refresh_from_db();self.assertEqual(row.description,'Administrator edit')
        self.assertFalse(CertificateRelease.objects.get(edition=self.edition).enabled)

    def test_approved_houses_populate_with_stable_keys_and_existing_drafts_are_not_recreated(self):
        from .house_configuration import approved_2026_houses
        from .management.commands.initialize_dic2026_release import LEGACY_KEYS, canonical
        first = initialize(self.edition, self.owner)
        self.assertEqual(first, 180)
        houses = list(House.objects.filter(edition=self.edition))
        self.assertEqual(len(houses), 8)
        self.assertEqual(sum(row.capacity for row in houses), 240)
        self.assertEqual({h.name for h in houses}, {h['name'] for h in approved_2026_houses()})
        self.assertEqual({h.canonical_key for h in houses}, set(LEGACY_KEYS.values()))
        self.assertEqual({h.gender for h in houses}, {'female', 'male'})
        self.assertFalse(self.edition.allocation_strategy == 'balanced')
        existing = houses[0]
        existing.eligibility_notes = 'Staff-customized description'
        existing.save(update_fields=['eligibility_notes'])
        self.assertEqual(initialize(self.edition, self.owner), 0)
        existing.refresh_from_db()
        self.assertEqual(existing.eligibility_notes, 'Staff-customized description')
        self.assertEqual(TimetableEntry.objects.filter(edition=self.edition).count(), first)
        self.assertFalse(TimetableEntry.objects.filter(edition=self.edition,description__icontains='Millionaire').exists())
        self.assertTrue(TimetableEntry.objects.filter(edition=self.edition,date=date(2026,12,31),title='Explanation of Ahsanul Akhlaq',certainty='confirmed').exists())
        self.assertTrue(TimetableEntry.objects.filter(edition=self.edition,timetable_type='food',date=date(2026,12,23),meal='lunch').exists())

    def test_excluded_game_migration_changes_only_exact_untouched_drafts(self):
        from django.apps import apps
        from django.db import connection
        from importlib import import_module
        reconcile = import_module(
            'dic.migrations.0043_exclude_dic2026_millionaire_drafts'
        ).remove_unmodified_excluded_drafts
        excluded = TimetableEntry.objects.create(
            edition=self.edition, date=date(2026,12,24), day_number=2,
            timetable_type='activities', source_key='dic2026:activities:2:13',
            description='Individual Millionaire- Challenge: Ta’lim & Tahdheeb',
            time_label='17:00–18:30', certainty='unspecified',
            modified_by=self.owner)
        edited = TimetableEntry.objects.create(
            edition=self.edition, date=date(2026,12,25), day_number=3,
            timetable_type='activities', source_key='dic2026:activities:3:13',
            description='Staff-edited alternative: still under review',
            time_label='17:00–18:30', certainty='unspecified',
            modified_by=self.owner)
        food = TimetableEntry.objects.create(
            edition=self.edition, date=date(2026,12,23), day_number=1,
            timetable_type='food', meal='lunch',
            source_key='dic2026:food:1:0', description='Officials’ lunch',
            time_label='Lunch', certainty='confirmed',
            modified_by=self.owner)
        from types import SimpleNamespace
        editor = SimpleNamespace(connection=connection)
        reconcile(apps, editor)
        reconcile(apps, editor)
        self.assertFalse(TimetableEntry.objects.filter(pk=excluded.pk).exists())
        self.assertTrue(TimetableEntry.objects.filter(pk=edited.pk).exists())
        self.assertTrue(TimetableEntry.objects.filter(pk=food.pk).exists())

    def test_legacy_unconfigured_matching_house_is_completed_without_renaming(self):
        from .management.commands.initialize_dic2026_release import LEGACY_KEYS, canonical
        from .house_configuration import approved_2026_houses
        row = approved_2026_houses()[0]
        legacy = House.objects.create(edition=self.edition, name=row['name'],
                                      gender=row['gender'], canonical_key=LEGACY_KEYS[canonical(row['name'])])
        pk = legacy.pk
        initialize(self.edition, self.owner)
        legacy.refresh_from_db()
        self.assertEqual(legacy.pk, pk)
        self.assertEqual(legacy.capacity, 30)
        self.assertEqual(legacy.badge_colour, row['badge_colour'])
        self.assertEqual(House.objects.filter(edition=self.edition).count(), 8)

    def test_conflicting_house_inventory_fails_atomically_and_preserves_records(self):
        House.objects.create(edition=self.edition, name='Unexpected extra house', gender='male', capacity=30)
        with self.assertRaises(CommandError):
            initialize(self.edition, self.owner)
        self.assertEqual(TimetableEntry.objects.filter(edition=self.edition).count(), 0)
        self.assertEqual(House.objects.filter(edition=self.edition).count(), 1)
        self.edition.refresh_from_db()
        self.assertEqual(self.edition.housing_age_reference_date, date(2026, 12, 23))

    def test_approved_revisions_and_audience_parallel_slots_publish_without_overlap(self):
        initialize(self.edition,self.owner)
        monday=TimetableEntry.objects.filter(date=date(2026,12,28),timetable_type='activities')
        self.assertEqual(monday.filter(start_time=time(11),gender='female').get().title,'Sisters’ Workshop')
        self.assertEqual(monday.filter(start_time=time(11),gender='male').get().title,'Sports')
        self.assertFalse(monday.filter(description__icontains='Seerah').exists())
        thursday=TimetableEntry.objects.filter(date=date(2026,12,31),timetable_type='activities')
        self.assertEqual(thursday.get(time_label='After Asr').title,'Evening of Gratitude')
        self.assertIn('Campus Challenge',thursday.get(time_label='After Isha').description)
        # Imported activities are not all committee-confirmed: publishing
        # must fail closed until the entire date is explicitly approved.
        with self.assertRaises(ValidationError):
            publish_days(self.owner, monday, True)
        self.assertFalse(monday.filter(status='published').exists())
        monday.update(certainty='confirmed')  # Synthetic committee approval in disposable CI only.
        publish_days(self.owner,monday,True)
        self.assertTrue(monday.filter(status='published').exists())

    def test_camper_housing_refresh_is_optional_and_awaiting_does_not_block_portal(self):
        from django.urls import reverse
        client, _ = self.login()
        with override_settings(DIC_AUTOMATION_ACTOR_ID=0, DAWANA_WEBSITE_ONLY=False):
            refreshed = self.post(client, 'participant-housing-refresh', {})
            self.assertEqual(refreshed.status_code, 200, refreshed.content)
            self.assertEqual(refreshed.json()['housing'], 'awaiting_or_updated')
        visible = client.get(reverse('dic:participant-enrollments'))
        self.assertEqual(visible.status_code, 200, visible.content)
        campers = [person for order in visible.json()['orders']
                   for person in order['participants']]
        self.assertTrue(campers)
        self.assertIn('housing', campers[0])
        self.assertEqual(campers[0]['housing']['status'], 'awaiting')
        self.assertEqual(campers[0]['housing']['message'], 'Awaiting house allocation')

    def test_published_timetable_scoped_to_gender_and_lagos_midnight(self):
        initialize(self.edition,self.owner)
        monday=TimetableEntry.objects.filter(date=date(2026,12,28),timetable_type='activities')
        with self.assertRaises(ValidationError):
            publish_days(self.owner,monday,True)
        monday.update(certainty='confirmed')  # Test-only approval, never production data.
        publish_days(self.owner,monday,True)
        client,_=self.login()
        path=reverse('dic:participant-timetables')
        from .models import ParticipantPortalGrant
        ParticipantPortalGrant.objects.update(expires_at=datetime(2027,1,2,tzinfo=utc.utc))
        with patch('dic.timetable_api.timezone.now',return_value=datetime(2026,12,27,23,5,tzinfo=utc.utc)):
            response=client.get(path,{'item_id':self.item.pk})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['today'],'2026-12-28')
        self.assertTrue(any(row['title']=='Sports' for row in response.json()['entries']))
        self.assertFalse(any('Sisters' in row['title'] for row in response.json()['entries']))
        foreign=self.unpaid_order.items.first()
        self.assertEqual(client.get(path,{'item_id':foreign.pk}).status_code,403)

    def test_resources_unpublished_and_foreign_objects_are_not_accessible(self):
        client,_=self.login()
        recording=LectureRecording.objects.create(edition=self.edition,title='Private draft',audio='camp-recordings/synthetic.mp3')
        url=reverse('dic:camper-recording',args=['audio',recording.pk])
        self.assertEqual(client.get(url,{'item_id':self.item.pk}).status_code,404)
        response=client.get(reverse('dic:camper-resources'),{'item_id':self.item.pk})
        self.assertEqual(response.json()['recordings'],[])
        self.assertFalse(response.json()['certificate']['available'])
        recording.state='published';recording.save(actor=self.owner)
        self.assertEqual(len(client.get(reverse('dic:camper-resources'),{'item_id':self.item.pk}).json()['recordings']),1)
        recording.state='draft';recording.save(actor=self.owner)
        self.assertEqual(client.get(url,{'item_id':self.item.pk}).status_code,404)
        self.assertEqual(Client().get(url,{'item_id':self.item.pk}).status_code,403)

    def test_certificate_release_no_early_access_stable_reference_and_names(self):
        from .certificates import issue,release_for
        config=CertificateRelease.objects.create(edition=self.edition)
        client,_=self.login();url=reverse('dic:camper-certificate')
        self.assertEqual(client.get(url,{'item_id':self.item.pk}).status_code,403)
        config.release_at=datetime(2027,1,1,10,tzinfo=utc.utc);config.enabled=True;config.artwork_sha256='a'*64;config.name_box=[100,200,640,100];config.reference_box=[100,40,640,50];config.save()
        with patch('dic.certificates.approved_artwork',return_value='approved'),patch('dic.certificates.timezone.now',return_value=datetime(2027,1,1,11,tzinfo=utc.utc)):
            first=issue(self.item);second=issue(self.item)
            self.assertEqual(first.reference,second.reference)
            self.assertEqual(first.participant_name,self.item.participant.full_name)
            first.revoked_at=datetime.now(utc.utc);first.save()
            from rest_framework.exceptions import PermissionDenied
            with self.assertRaises(PermissionDenied):issue(self.item)
        self.assertEqual(ParticipationCertificate.objects.count(),1)

    def test_certificate_artwork_missing_blocks_release_and_long_names_fit_legibly(self):
        from .certificates import approved_artwork,fitted_lines
        config=CertificateRelease.objects.create(edition=self.edition)
        with self.assertRaises(ValidationError):approved_artwork(config)
        size,lines=fitted_lines('A very long participant name with many authoritative components','Helvetica',600,120)
        self.assertGreaterEqual(size,16);self.assertLessEqual(len(lines)*size*1.25,120)

    def test_staff_roles_actual_login_permitted_and_forbidden_endpoints(self):
        call_command('initialize_dic_committee_roles',apply=True,approved_by=self.owner.username)
        from django.contrib.auth.models import Group
        officer=get_user_model().objects.create_user('committee-checkin',password='synthetic-pass',is_staff=True)
        officer.groups.add(Group.objects.get(name='DIC Check-in Officers'))
        client=Client(enforce_csrf_checks=True)
        token=client.get(reverse('dic:operations-csrf')).json()['csrfToken']
        response=client.post(reverse('dic:operations-login'),{'username':officer.username,'password':'synthetic-pass'},content_type='application/json',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(client.get(reverse('dic:operations-check-in')).status_code,200)
        self.assertEqual(client.get(reverse('dic:operations-finance')).status_code,403)
        officer.is_active=False;officer.save(update_fields=['is_active'])
        self.assertEqual(client.get(reverse('dic:operations-check-in')).status_code,403)

    def test_r2_path_traversal_and_configuration_are_rejected_without_network(self):
        from .recording_storage import safe_key
        from .storage_configuration import production_storage
        from types import SimpleNamespace
        from django.core.exceptions import ImproperlyConfigured
        for key in ('../secret','/absolute','a/../secret','a'+chr(92)+'b','a'+chr(0)+'b','C:secret'):
            with self.assertRaises(ValidationError):safe_key(key)
            with self.assertRaises(ValidationError):
                CertificateRelease(edition=self.edition,artwork=key+'.png').full_clean()
        with self.assertRaises(ImproperlyConfigured):production_storage(SimpleNamespace(),'media')

    def test_recording_stream_and_download_require_current_publication(self):
        import wave
        with tempfile.TemporaryDirectory() as root,override_settings(DEBUG=True,DIC_MEMORY_STORAGE='local',DIC_MEMORY_LOCAL_ROOT=root):
            folder=Path(root)/'camp-recordings';folder.mkdir()
            with wave.open(str(folder/'test.wav'),'wb') as audio:
                audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000);audio.writeframes(b'\x00\x00'*800)
            row=LectureRecording.objects.create(edition=self.edition,title='Approved audio',audio='camp-recordings/test.wav')
            row.state='published';row.save(actor=self.owner)
            client,_=self.login();url=reverse('dic:camper-recording',args=['audio',row.pk])
            response=client.get(url,{'item_id':self.item.pk,'download':'1'})
            self.assertEqual(response.status_code,200)
            self.assertIn('attachment',response['Content-Disposition'])
            self.assertTrue(b''.join(response.streaming_content).startswith(b'RIFF'))
            row.state='draft';row.save(actor=self.owner)
            self.assertEqual(client.get(url,{'item_id':self.item.pk}).status_code,404)

    def test_media_editor_admin_forms_render_without_private_object_urls(self):
        call_command('initialize_dic_committee_roles',apply=True,approved_by=self.owner.username)
        from django.contrib.auth.models import Group
        editor=get_user_model().objects.create_user('media-editor',password='synthetic',is_staff=True)
        editor.groups.add(Group.objects.get(name='DIC Media Editors'))
        row=LectureRecording.objects.create(edition=self.edition,title='Draft preview',audio='camp-recordings/test.mp3')
        self.client.force_login(editor)
        response=self.client.get(reverse('admin:dic_lecturerecording_change',args=[row.pk]))
        self.assertEqual(response.status_code,200)
        self.assertNotIn('r2.cloudflarestorage.com',response.content.decode())
        row.state='published'
        with self.assertRaises(ValidationError):row.save(actor=editor)

    def test_email_signin_is_explicit_verified_and_never_links_shared_contact_accounts(self):
        from .models import PortalAccount,PortalAccountBooking
        user=get_user_model().objects.create_user('verified-camper',password='synthetic')
        account=PortalAccount.objects.create(user=user,username_key=user.username,contact_channel='identity',contact_digest='a'*64)
        PortalAccountBooking.objects.create(account=account,order=self.paid_order)
        client,_=self.login()
        response=self.post(client,'portal-email-verify',{'email':self.paid_order.primary_registrant.email,'password':'synthetic'})
        self.assertEqual(response.status_code,200,response.content)
        from .portal_accounts import password_account
        self.assertEqual(password_account(self.paid_order.primary_registrant.email,'synthetic').pk,account.pk)
        self.assertEqual(PortalAccountBooking.objects.count(),1)

    def test_certificate_renderer_personalizes_test_fixture_without_shipping_artwork(self):
        # This blank in-memory QA fixture is never stored at the approved artwork path.
        from PIL import Image
        from .certificates import render_certificate
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic-test-only.png';Image.new('RGB',(842,595),'white').save(path)
            config=SimpleNamespace(page_width=842,page_height=595,name_box=[100,220,640,120],reference_box=[100,60,640,50])
            record=SimpleNamespace(reference='synthetic-reference',participant_name='Amina Adéwálé Long Authoritative Participant Name',edition=self.edition)
            with patch('dic.certificates.approved_artwork',return_value=str(path)):
                payload=render_certificate(record,config)
            from pypdf import PdfReader
            text=PdfReader(io.BytesIO(payload)).pages[0].extract_text()
            self.assertIn('Adéwálé',text);self.assertIn('synthetic-reference',text)
