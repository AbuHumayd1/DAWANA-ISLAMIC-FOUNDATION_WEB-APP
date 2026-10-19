import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch

from django.core.exceptions import ValidationError as ModelValidationError
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .test_participant_portal import PortalFixtures, TEST_DELIVERY
from .models import CampEdition, CampEnrollment, RegistrationCategory, ParticipantPortalChallenge, DICAdminAuditEvent
from .participant_services import ensure_enrollment, eligibility, id_command
from .management.commands.send_dic_portal_messages import process_portal_challenge
from .recovery import RecoveryDeliveryError


@override_settings(**TEST_DELIVERY)
class ParticipantRemediationTests(PortalFixtures, TestCase):
    def queued(self):
        client = Client(enforce_csrf_checks=True)
        response = self.post(client, 'participant-challenges', {
            'channel': 'email', 'contact': self.paid_order.primary_registrant.email,
            'order_reference': str(self.paid_order.public_id)})
        self.assertEqual(response.status_code, 202)
        return ParticipantPortalChallenge.objects.get(pk=response.json()['challenge_id'])

    def test_original_category_reassignment_rejected_by_domain_and_database(self):
        enrollment = ensure_enrollment(self.item.pk)
        issue = id_command(enrollment.pk, 'issue')
        number = enrollment.participant_number
        other = CampEdition.objects.create(name='Other edition', year=2098,
            camp_start_date=self.edition.camp_start_date, camp_end_date=self.edition.camp_end_date)
        self.category.edition = other
        with self.assertRaises(ModelValidationError):
            self.category.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.category.save(update_fields=['edition'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegistrationCategory.objects.filter(pk=self.category.pk).update(edition=other)
        self.category.refresh_from_db()
        self.assertEqual(self.category.edition_id, self.edition.pk)
        self.assertTrue(eligibility(enrollment)['eligible'])
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.participant_number, number)
        self.assertEqual(enrollment.id_issues.get().pk, issue.pk)
        self.category.name = 'Allowed category name correction'
        self.category.full_clean()
        self.category.save()

    def test_inconsistent_legacy_source_fails_closed_even_with_cached_enrollment(self):
        enrollment = ensure_enrollment(self.item.pk)
        self.category.edition_id = self.edition.pk + 999
        self.item.category = self.category
        with patch('dic.participant_services.RegistrationOrderItem.objects.select_related') as query:
            query.return_value.get.return_value = self.item
            self.assertEqual(eligibility(enrollment), {'eligible': False, 'code': 'invalid_source'})
        enrollment.source_item = self.item
        with self.assertRaises(ModelValidationError):
            enrollment.clean()

    def test_delivery_replay_and_failed_send_are_never_retried(self):
        challenge = self.queued()
        with patch('dic.management.commands.send_dic_portal_messages.send_recovery_code', side_effect=RecoveryDeliveryError('unavailable')) as sender:
            self.assertEqual(process_portal_challenge(challenge.pk), 'failed')
            self.assertEqual(process_portal_challenge(challenge.pk), 'skipped')
            sender.assert_called_once()
        challenge.refresh_from_db()
        self.assertEqual(challenge.delivery_status, 'failed')
        self.assertEqual(challenge.encrypted_delivery_payload, '')

    def test_old_claim_is_not_reclaimed_and_cleanup_closes_expired_claim(self):
        challenge = self.queued()
        ParticipantPortalChallenge.objects.filter(pk=challenge.pk).update(
            delivery_status='processing', delivery_started_at=timezone.now()-timedelta(minutes=4))
        with patch('dic.management.commands.send_dic_portal_messages.send_recovery_code') as sender:
            call_command('send_dic_portal_messages', limit=50)
            sender.assert_not_called()
        ParticipantPortalChallenge.objects.filter(pk=challenge.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        call_command('cleanup_dic_participant_access')
        challenge.refresh_from_db()
        self.assertEqual(challenge.delivery_status, 'suppressed')
        self.assertEqual(challenge.encrypted_delivery_payload, '')
        self.assertEqual(process_portal_challenge(challenge.pk), 'skipped')

    def test_consumed_during_send_cannot_be_finalized_as_sent(self):
        challenge = self.queued()
        def consume(*args):
            ParticipantPortalChallenge.objects.filter(pk=challenge.pk).update(consumed_at=timezone.now())
        with patch('dic.management.commands.send_dic_portal_messages.send_recovery_code', side_effect=consume):
            self.assertEqual(process_portal_challenge(challenge.pk), 'suppressed')
        with patch('dic.management.commands.send_dic_portal_messages.send_recovery_code') as sender:
            self.assertEqual(process_portal_challenge(challenge.pk), 'skipped')
            sender.assert_not_called()

    def test_booking_and_staff_list_reads_audited_without_search_or_contact_payload(self):
        client, _ = self.login()
        self.assertEqual(client.get(reverse('dic:participant-enrollments')).status_code, 200)
        event = DICAdminAuditEvent.objects.get(action='participant_bookings_viewed')
        self.assertEqual(event.details['order_count'], 1)
        self.assertEqual(event.details['participant_count'], 2)
        staff = Client(); staff.force_login(self.id_manager)
        self.assertEqual(staff.get(reverse('dic:operations-enrollments'), {'q': 'Sensitive Search'}).status_code, 200)
        event = DICAdminAuditEvent.objects.get(action='staff_participant_ids_searched')
        self.assertEqual(event.actor_id, self.id_manager.pk)
        self.assertTrue(event.details['searched'])
        self.assertNotIn('Sensitive Search', str(event.details))
        self.assertNotIn(self.paid_order.primary_registrant.email, str(event.details))
        operator = Client(); operator.force_login(self.operator)
        before = DICAdminAuditEvent.objects.filter(action='staff_participant_ids_searched').count()
        self.assertEqual(operator.get(reverse('dic:operations-enrollments')).status_code, 403)
        self.assertEqual(DICAdminAuditEvent.objects.filter(action='staff_participant_ids_searched').count(), before)


@override_settings(**TEST_DELIVERY)
class PortalDeliveryConcurrencyTests(PortalFixtures, TransactionTestCase):
    def test_concurrent_claimants_do_not_send_or_overwrite_twice(self):
        client = Client(enforce_csrf_checks=True)
        response = self.post(client, 'participant-challenges', {'channel': 'email',
            'contact': self.paid_order.primary_registrant.email, 'order_reference': str(self.paid_order.public_id)})
        challenge_id = response.json()['challenge_id']
        started, release = Event(), Event()
        def send(*args):
            started.set()
            if not release.wait(15):
                raise AssertionError('Delivery concurrency synchronization timed out')
        def worker():
            close_old_connections()
            try:
                return process_portal_challenge(challenge_id)
            finally:
                close_old_connections()
        with patch('dic.management.commands.send_dic_portal_messages.send_recovery_code', side_effect=send) as sender:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(worker)
                try:
                    self.assertTrue(started.wait(10))
                    # Simulate work older than the former lease while still active.
                    ParticipantPortalChallenge.objects.filter(pk=challenge_id).update(delivery_started_at=timezone.now()-timedelta(minutes=4))
                    self.assertEqual(pool.submit(worker).result(timeout=10), 'skipped')
                    call_command('send_dic_portal_messages', limit=50)
                finally:
                    release.set()
                self.assertEqual(first.result(timeout=10), 'sent')
            sender.assert_called_once()
        self.assertEqual(ParticipantPortalChallenge.objects.get(pk=challenge_id).delivery_status, 'sent')
        self.assertEqual(process_portal_challenge(challenge_id), 'skipped')
