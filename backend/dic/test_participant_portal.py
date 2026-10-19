import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from . import test_operations_portal as fixtures
from .management.commands.send_dic_portal_messages import process_portal_challenge
from .models import (CampEnrollment, DigitalIDIssue, ParticipantPortalChallenge, ParticipantPortalGrant,
                     ParticipantPortalScope, RegistrationOrder, RegistrationOrderItem, RegistrationRecoveryRateLimit,
                     PaymentAttempt, Participant, DICAdminAuditEvent)
from .participant_api import COOKIE, BROWSER_COOKIE, COOKIE_PATH
from .participant_services import ensure_enrollment, eligibility, id_command
from .recovery import decrypt_delivery_payload

TEST_DELIVERY = dict(DIC_RECOVERY_DELIVERY_WORKER_ENABLED=True, DIC_RECOVERY_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                     DIC_EMAIL_RECOVERY_ENABLED=True, DEFAULT_FROM_EMAIL='test@example.test', EMAIL_HOST='smtp.example.test',
                     EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend')


class PortalFixtures:
    create_user = fixtures.DICOperationsPortalTests.create_user
    make_order = fixtures.DICOperationsPortalTests.make_order

    def setUp(self):
        fixtures.DICOperationsPortalTests.setUp(self)
        from .pricing import create_price_revision, current_order_prices
        revision = create_price_revision(self.paid_order, current_order_prices(self.paid_order), accepted_at=timezone.now())
        attempt = self.paid_order.payment_attempts.get()
        attempt.price_revision = revision
        attempt.provider_transaction_id = str(uuid.uuid4())
        attempt.verified_at = timezone.now()
        attempt.save()
        self.item = self.paid_order.items.first()
        self.id_manager = self.create_user('test-id-manager', 'test-only', 'can_view_dic_operations', 'can_view_dic_ids', 'can_manage_dic_ids')
        self.id_manager.user_permissions.add(*Permission.objects.filter(content_type__app_label='dic', codename__in=('can_view_dic_ids', 'can_manage_dic_ids')))

    def csrf(self, client):
        return client.get(reverse('dic:participant-csrf')).json()['csrfToken']

    def post(self, client, name, body):
        return client.post(reverse('dic:' + name), body, content_type='application/json', HTTP_X_CSRFTOKEN=self.csrf(client))

    def challenge(self, client, order=None, contact=None):
        order = order or self.paid_order
        result = self.post(client, 'participant-challenges', {'channel': 'email', 'contact': contact or order.primary_registrant.email, 'order_reference': str(order.public_id)})
        self.assertEqual(result.status_code, 202, result.content)
        challenge = ParticipantPortalChallenge.objects.get(pk=result.json()['challenge_id'])
        code = decrypt_delivery_payload(challenge.encrypted_delivery_payload)['code']
        with patch('dic.management.commands.send_dic_portal_messages.send_recovery_code') as sender:
            process_portal_challenge(challenge.pk)
            if challenge.order_id:
                sender.assert_called_once()
        return challenge, code

    def login(self, client=None):
        client = client or Client(enforce_csrf_checks=True)
        challenge, code = self.challenge(client)
        response = self.post(client, 'participant-verify', {'challenge_id': str(challenge.pk), 'code': code})
        self.assertEqual(response.status_code, 200, response.content)
        return client, response


@override_settings(**TEST_DELIVERY)
class ParticipantPortalTests(PortalFixtures, TestCase):
    def test_otp_session_scope_multi_participant_and_minimal_payload(self):
        client, response = self.login()
        self.assertNotIn('token', str(response.json()).lower())
        self.assertTrue(response.cookies[COOKIE]['httponly'])
        self.assertEqual(response.cookies[COOKIE]['path'], COOKIE_PATH)
        self.assertEqual(response.cookies[COOKIE]['samesite'], 'Lax')
        self.assertFalse(client.cookies.get('sessionid'))
        data = client.get(reverse('dic:participant-enrollments')).json()
        self.assertEqual(len(data['orders']), 1)
        self.assertEqual(len(data['orders'][0]['participants']), 2)
        for forbidden in ('date_of_birth', 'address', 'phone', 'height', 'weight', 'access_token', 'guardian'):
            self.assertNotIn(forbidden, str(data))
        self.assertEqual(CampEnrollment.objects.count(), 0)  # reads never create IDs
        self.assertEqual(client.get(reverse('dic:operations-dashboard')).status_code, 403)
        self.assertEqual(client.get('/admin/').status_code, 302)

    def test_invalid_expired_reused_and_browser_bound_otp(self):
        client = Client(enforce_csrf_checks=True)
        challenge, code = self.challenge(client)
        stranger = Client(enforce_csrf_checks=True)
        payload = {'challenge_id': str(challenge.pk), 'code': code}
        self.assertEqual(self.post(stranger, 'participant-verify', payload).status_code, 400)
        self.assertEqual(self.post(client, 'participant-verify', {**payload, 'code': '000000' if code != '000000' else '111111'}).status_code, 400)
        self.assertEqual(self.post(client, 'participant-verify', payload).status_code, 200)
        self.assertEqual(self.post(client, 'participant-verify', payload).status_code, 400)
        RegistrationRecoveryRateLimit.objects.all().delete()
        challenge, code = self.challenge(client)
        ParticipantPortalChallenge.objects.filter(pk=challenge.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.post(client, 'participant-verify', {'challenge_id': str(challenge.pk), 'code': code}).status_code, 400)

    def test_attempt_limits_commit_and_never_issue_grants(self):
        client = Client(enforce_csrf_checks=True)
        challenge, code = self.challenge(client)
        for _ in range(5):
            result = self.post(client, 'participant-verify', {'challenge_id': str(challenge.pk), 'code': '000000' if code != '000000' else '111111'})
            self.assertEqual(result.status_code, 400)
        challenge.refresh_from_db()
        self.assertEqual(challenge.attempts, 5)
        self.assertIsNotNone(challenge.consumed_at)
        self.assertEqual(self.post(client, 'participant-verify', {'challenge_id': str(challenge.pk), 'code': code}).status_code, 400)
        self.assertEqual(ParticipantPortalGrant.objects.count(), 0)

    def test_request_throttle_and_generic_unknown_booking(self):
        client = Client(enforce_csrf_checks=True)
        body = {'channel': 'email', 'contact': 'unknown@example.test', 'order_reference': str(uuid.uuid4())}
        unknown = self.post(client, 'participant-challenges', body)
        self.assertEqual(unknown.status_code, 202)
        first = ParticipantPortalChallenge.objects.get(pk=unknown.json()['challenge_id'])
        self.assertIsNone(first.order)
        with patch('dic.management.commands.send_dic_portal_messages.send_recovery_code') as sender:
            self.assertEqual(process_portal_challenge(first.pk), 'suppressed')
            sender.assert_not_called()
        self.assertEqual(self.post(client, 'participant-challenges', body).status_code, 429)
        RegistrationRecoveryRateLimit.objects.all().delete()
        known = self.post(client, 'participant-challenges', {'channel': 'email', 'contact': self.paid_order.primary_registrant.email, 'order_reference': str(self.paid_order.public_id)})
        self.assertEqual(set(known.json()), set(unknown.json()))
        self.assertEqual(known.json()['detail'], unknown.json()['detail'])
        self.assertNotIn('code', known.json())

    @override_settings(DIC_EMAIL_RECOVERY_ENABLED=False)
    def test_unavailable_channel_is_reported_honestly(self):
        client = Client(enforce_csrf_checks=True)
        self.assertFalse(client.get(reverse('dic:participant-options')).json()['channels'][0]['available'])
        self.assertEqual(self.post(client, 'participant-challenges', {'channel': 'email', 'contact': self.paid_order.primary_registrant.email, 'order_reference': str(self.paid_order.public_id)}).status_code, 503)

    def test_cross_booking_matching_contact_is_not_automatically_combined(self):
        self.unpaid_order.primary_registrant.email = self.paid_order.primary_registrant.email
        self.unpaid_order.primary_registrant.save()
        client, _ = self.login()
        data = client.get(reverse('dic:participant-enrollments')).json()
        self.assertEqual([o['reference'] for o in data['orders']], [str(self.paid_order.public_id)])
        other_item = self.unpaid_order.items.first()
        self.assertEqual(self.post(client, 'participant-enrollments', {'registration_item_id': other_item.pk}).status_code, 404)
        other_enrollment = ensure_enrollment(other_item.pk)
        self.assertEqual(client.get(reverse('dic:participant-id', args=[other_enrollment.pk])).status_code, 404)

    def test_staff_and_portal_sessions_coexist_and_logout_is_isolated(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.operator)
        session = client.cookies['sessionid'].value
        client, _ = self.login(client)
        self.assertEqual(client.cookies['sessionid'].value, session)
        self.assertEqual(client.get(reverse('dic:operations-dashboard')).status_code, 200)
        self.assertEqual(self.post(client, 'participant-logout', {}).status_code, 204)
        self.assertEqual(client.get(reverse('dic:participant-me')).status_code, 403)
        self.assertEqual(client.get(reverse('dic:operations-dashboard')).status_code, 200)

    def test_session_rotation_expiry_scope_revocation_and_contact_change(self):
        client, _ = self.login()
        previous = client.cookies[COOKIE].value
        RegistrationRecoveryRateLimit.objects.all().delete()
        client, _ = self.login(client)
        self.assertNotEqual(client.cookies[COOKIE].value, previous)
        replay = Client(); replay.cookies[COOKIE] = previous
        self.assertEqual(replay.get(reverse('dic:participant-me')).status_code, 403)
        ParticipantPortalScope.objects.update(revoked_at=timezone.now())
        self.assertEqual(client.get(reverse('dic:participant-enrollments')).json()['orders'], [])
        ParticipantPortalScope.objects.update(revoked_at=None)
        self.paid_order.primary_registrant.email = 'changed@example.test'
        self.paid_order.primary_registrant.save()
        self.assertEqual(client.get(reverse('dic:participant-enrollments')).json()['orders'], [])
        ParticipantPortalGrant.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(client.get(reverse('dic:participant-me')).status_code, 403)

    @override_settings(SESSION_COOKIE_SECURE=True)
    def test_csrf_and_secure_cookie_no_raw_bearer_in_response(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('dic:participant-challenges'), {}, content_type='application/json').status_code, 403)
        client, response = self.login(client)
        self.assertTrue(response.cookies[COOKIE]['secure'])
        self.assertEqual(client.post(reverse('dic:participant-logout'), {}, content_type='application/json').status_code, 403)
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_recovery_challenge_cannot_authenticate_portal_and_reverse(self):
        from .models import RegistrationRecoveryChallenge
        old = RegistrationRecoveryChallenge.objects.create(contact_digest='x'*64, code_digest='x'*64, channel='email', expires_at=timezone.now()+timedelta(minutes=10), resend_after=timezone.now())
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post(client, 'participant-verify', {'challenge_id': str(old.pk), 'code': '123456'}).status_code, 400)
        challenge, code = self.challenge(client)
        self.assertEqual(client.post(reverse('dic:recovery-verify', args=[challenge.pk]), {'code': code}, content_type='application/json').status_code, 400)

    def test_individual_issuance_reprint_card_fields_revocation_and_no_auto_reissue(self):
        client, _ = self.login()
        items = list(self.paid_order.items.all())
        numbers = []
        for item in items:
            result = self.post(client, 'participant-enrollments', {'registration_item_id': item.pk})
            self.assertEqual(result.status_code, 200, result.content)
            enrollment = CampEnrollment.objects.get(pk=result.json()['id'])
            numbers.append(enrollment.participant_number)
            card = client.get(reverse('dic:participant-id', args=[enrollment.pk]))
            self.assertEqual(card.status_code, 200)
            self.assertEqual(set(card.json()), {'name','participant_number','category','edition','starts','ends','venue','house','version','logo_url','branding_verified'})
            self.assertFalse(card.json()['branding_verified'])
            self.assertEqual(self.post(client, 'participant-enrollments', {'registration_item_id': item.pk}).status_code, 200)
            self.assertEqual(enrollment.id_issues.count(), 1)
        self.assertEqual(len(set(numbers)), 2)
        id_command(enrollment.pk, 'revoke', self.id_manager, 'Lost card')
        self.assertEqual(self.post(client, 'participant-enrollments', {'registration_item_id': item.pk}).status_code, 400)
        self.assertEqual(client.get(reverse('dic:participant-id', args=[enrollment.pk])).status_code, 400)
        replacement = id_command(enrollment.pk, 'reissue', self.id_manager, 'Approved replacement')
        self.assertEqual(replacement.version, 2)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.participant_number, numbers[-1])
        RegistrationOrder.objects.filter(pk=self.paid_order.pk).update(payment_status='refunded')
        self.assertEqual(client.get(reverse('dic:participant-id', args=[enrollment.pk])).status_code, 400)

    def test_eligibility_cases_and_legacy_review_without_mutation(self):
        enrollment = ensure_enrollment(self.item.pk)
        self.assertTrue(eligibility(enrollment)['eligible'])
        for status in ['pending', 'failed', 'refunded']:
            RegistrationOrder.objects.filter(pk=self.paid_order.pk).update(payment_status=status)
            self.assertFalse(eligibility(enrollment)['eligible'])
        RegistrationOrder.objects.filter(pk=self.paid_order.pk).update(payment_status='paid', status='cancelled')
        self.assertFalse(eligibility(enrollment)['eligible'])
        RegistrationOrder.objects.filter(pk=self.paid_order.pk).update(status='confirmed')
        PaymentAttempt.objects.filter(order=self.paid_order).update(provider_paid_at=None)
        self.assertEqual(eligibility(enrollment)['code'], 'settlement_evidence_review_required')
        PaymentAttempt.objects.filter(order=self.paid_order).update(provider_paid_at=timezone.now())
        PaymentAttempt.objects.create(order=self.paid_order, reference=str(uuid.uuid4()), amount_kobo=25000, status='failed')
        PaymentAttempt.objects.create(order=self.paid_order, reference=str(uuid.uuid4()), amount_kobo=25000, status='duplicate_success')
        self.assertTrue(eligibility(enrollment)['eligible'])
        unpaid = ensure_enrollment(self.unpaid_order.items.first().pk)
        RegistrationOrder.objects.filter(pk=self.unpaid_order.pk).update(status='confirmed', payment_status='paid')
        self.assertFalse(eligibility(unpaid)['eligible'])
        self.assertEqual(DigitalIDIssue.objects.count(), 0)
        RegistrationOrder.objects.filter(pk=self.paid_order.pk).update(current_price_revision=None)
        self.assertEqual(eligibility(enrollment)['code'], 'settlement_evidence_review_required')

    def test_ambiguity_and_cross_edition_database_guards(self):
        enrollment = ensure_enrollment(self.item.pk)
        duplicate = RegistrationOrderItem.objects.create(order=self.unpaid_order, participant=self.item.participant, category=self.category, category_name_snapshot=self.category.name, fee_snapshot_ngn=125, participant_snapshot={})
        self.assertEqual(ensure_enrollment(duplicate.pk).pk, enrollment.pk)
        self.assertEqual(eligibility(enrollment)['code'], 'source_review_required')
        other_participant = self.paid_order.items.exclude(pk=self.item.pk).first().participant
        with self.assertRaises(IntegrityError), transaction.atomic():
            CampEnrollment.objects.create(participant=other_participant, edition=self.edition, source_item=self.item, participant_number='INVALID')
        with self.assertRaises(IntegrityError), transaction.atomic():
            CampEnrollment.objects.filter(pk=enrollment.pk).update(participant_number='CHANGED')
        from .models import CampEdition
        other = CampEdition.objects.create(name='Other edition', year=2098, camp_start_date=self.edition.camp_start_date, camp_end_date=self.edition.camp_end_date)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CampEnrollment.objects.create(participant=self.item.participant, edition=other, source_item=self.item, participant_number='WRONG-EDITION')

    def test_number_collision_retries_and_active_issue_database_constraint(self):
        other = self.paid_order.items.exclude(pk=self.item.pk).first()
        with patch('dic.participant_services.secrets.choice', side_effect=list('A'*20 + 'B'*10)):
            first = ensure_enrollment(self.item.pk)
            second = ensure_enrollment(other.pk)
        self.assertNotEqual(first.participant_number, second.participant_number)
        current = id_command(first.pk, 'issue')
        with self.assertRaises(IntegrityError), transaction.atomic():
            DigitalIDIssue.objects.create(enrollment=first, version=2, expires_at=current.expires_at)
        DigitalIDIssue.objects.filter(pk=current.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            id_command(first.pk, 'issue')

    def test_staff_revocation_requires_csrf_and_own_permission(self):
        enrollment = ensure_enrollment(self.item.pk)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.operator)
        url = reverse('dic:operations-enrollment-id', args=[enrollment.pk])
        self.assertEqual(client.post(url, {'action': 'issue'}, content_type='application/json').status_code, 403)
        token = self.csrf(client)
        self.assertEqual(client.post(url, {'action': 'issue'}, content_type='application/json', HTTP_X_CSRFTOKEN=token).status_code, 403)
        self.operator.user_permissions.add(Permission.objects.get(content_type__app_label='dic', codename='can_manage_dic_ids'))
        self.assertEqual(client.post(url, {'action': 'issue'}, content_type='application/json', HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(client.post(url, {'action':'revoke','reason':'Reported lost'}, content_type='application/json', HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_worker_payload_scrubbing_cleanup_and_contact_revocation(self):
        client = Client(enforce_csrf_checks=True)
        challenge, _ = self.challenge(client)
        challenge.refresh_from_db()
        self.assertEqual(challenge.encrypted_delivery_payload, '')
        ParticipantPortalChallenge.objects.filter(pk=challenge.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        call_command('cleanup_dic_participant_access', limit=1)
        challenge.refresh_from_db()
        self.assertEqual(challenge.code_digest, '')

    def test_staff_permissions_review_revokes_id_and_groups_do_not_expand(self):
        enrollment = ensure_enrollment(self.item.pk)
        id_command(enrollment.pk, 'issue')
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('dic:operations-enrollments')).status_code, 403)
        for code in ['can_view_dic_ids', 'can_manage_dic_ids', 'can_review_dic_enrollment_sources']:
            self.operator.user_permissions.add(Permission.objects.get(codename=code, content_type__app_label='dic'))
        self.assertEqual(self.client.get(reverse('dic:operations-enrollments'), {'q': enrollment.participant_number}).status_code, 200)
        result = self.client.post(reverse('dic:operations-enrollment-id', args=[enrollment.pk]), {'action':'review_source', 'source_item_id':self.item.pk, 'restriction_reason':'Identity evidence review', 'reason':'Documented review'}, content_type='application/json')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['issue']['status'], 'revoked')
        self.assertFalse(result.json()['eligibility']['eligible'])
        call_command('setup_dic_staff_roles')
        self.assertFalse(Group.objects.get(name='DIC Administrators').permissions.filter(codename='can_manage_dic_ids').exists())
        self.assertTrue(DICAdminAuditEvent.objects.filter(action='enrollment_source_reviewed').exists())


class ParticipantIDConcurrencyTests(PortalFixtures, TransactionTestCase):
    def test_concurrent_enrollment_and_issuance_are_singletons(self):
        def enrollment_task(_):
            close_old_connections()
            try:
                return str(ensure_enrollment(self.item.pk).pk)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(enrollment_task, range(2)))
        self.assertEqual(ids[0], ids[1])
        def issue_task(_):
            close_old_connections()
            try:
                return str(id_command(ids[0], 'issue').pk)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            issues = list(pool.map(issue_task, range(2)))
        self.assertEqual(issues[0], issues[1])
        self.assertEqual(CampEnrollment.objects.count(), 1)
        self.assertEqual(DigitalIDIssue.objects.count(), 1)
        self.assertEqual(Participant.objects.count(), 3)
