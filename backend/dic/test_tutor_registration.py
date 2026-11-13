"""Tutor policy tests are database-free; integration requires a fresh tutor receipt."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import re
import secrets
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient
from .test_registration_privacy import camper
from .tutor_registration_api import TutorParticipantInput
from .tutor_registration import (require_authorizer, valid_invitation, validate_tutor,
    authorize, issue, revoke, redeem)
from .models import (CampEdition, TutorRegistrationAuthorization, TutorVerification,
    Participant, PaymentAttempt, RegistrationOrderPriceRevision, DICAdminAuditEvent,
    CampEnrollment, CampCheckIn, House, HouseAllocation, ParticipantPortalGrant, ParticipantPortalScope)
from .security import digest_value
from .participant_services import eligibility, id_command


def grant_synthetic_permissions(actor, model, codenames):
    """Test-only grants with real, transaction-local canonical content types.

    get_for_model() caches rows beyond TestCase rollback. Never use its cached
    primary keys to create permissions in a later transaction.
    """
    ContentType.objects.clear_cache()
    opts = model._meta
    declared = dict(opts.permissions)
    if not set(codenames) <= declared.keys():
        raise AssertionError('Synthetic grants must use permissions declared by their owning model.')
    content_type, _ = ContentType.objects.get_or_create(app_label=opts.app_label, model=opts.model_name)
    permissions = [Permission.objects.get_or_create(content_type=content_type, codename=code,
        defaults={'name': declared[code]})[0] for code in codenames]
    actor.user_permissions.add(*permissions)
    # M2M changes and refresh_from_db() do not invalidate ModelBackend caches.
    for key in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
        actor.__dict__.pop(key, None)
    getattr(actor, '_prefetched_objects_cache', {}).pop('user_permissions', None)


def tutor_data(**changes):
    raw = camper(full_name='Synthetic Tutor', email='tutor@example.test',
                 age_declaration='adult', date_of_birth=None, height_cm='', weight_kg='')
    raw.pop('category_id')
    raw.update(changes)
    serializer = TutorParticipantInput(data=raw)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class TutorPolicyTests(SimpleTestCase):
    def test_tutor_mutations_have_rate_limits_and_strict_input(self):
        from rest_framework.test import APIRequestFactory
        from rest_framework.throttling import ScopedRateThrottle
        from .tutor_registration_api import TutorRedeemView
        with patch.object(ScopedRateThrottle, 'allow_request', return_value=False), patch.object(ScopedRateThrottle, 'wait', return_value=1):
            response = TutorRedeemView.as_view()(APIRequestFactory().post('/api/v1/dic/tutor-registration/redeem/', {}, format='json'))
        self.assertEqual(response.status_code, 429)
    def test_authorization_requires_explicit_active_staff_permission(self):
        for active, staff, permission in [(False, True, True), (True, False, True), (True, True, False)]:
            actor = SimpleNamespace(is_authenticated=True, is_active=active, is_staff=staff, has_perm=lambda p: permission)
            with self.subTest(active=active, staff=staff, permission=permission), self.assertRaises(PermissionDenied):
                require_authorizer(actor)
        require_authorizer(SimpleNamespace(is_authenticated=True, is_active=True, is_staff=True,
            has_perm=lambda p: p == 'dic.can_authorize_dic_tutors'))

    def test_invitation_expiry_boundary_and_enablement(self):
        now = timezone.now()
        auth = SimpleNamespace(invitation_digest='digest', revoked_at=None, redeemed_at=None,
            expires_at=now + timedelta(seconds=1), edition=SimpleNamespace(tutor_registration_enabled=True,
                is_active=True, camp_end_date=timezone.localdate() + timedelta(days=1)))
        self.assertTrue(valid_invitation(auth, now))
        self.assertFalse(valid_invitation(auth, auth.expires_at))
        auth.edition.tutor_registration_enabled = False
        self.assertFalse(valid_invitation(auth, now))

    def test_tutor_adult_private_and_optional_measurements(self):
        result = tutor_data()
        self.assertIsNone(result['height_cm']); self.assertIsNone(result['weight_kg'])
        validate_tutor(result, SimpleNamespace(email='tutor@example.test', intended_name='Synthetic Tutor'))

    def test_underage_tutor_rejected_even_in_legacy_exact_mode(self):
        data = tutor_data(age_declaration='exact', date_of_birth=timezone.localdate().isoformat())
        with self.assertRaises(ValidationError):
            validate_tutor(data, SimpleNamespace(email='tutor@example.test', intended_name='Synthetic Tutor'))

    def test_identity_and_contact_cannot_be_overridden(self):
        for changes in [dict(email='other@example.test'), dict(full_name='Different Tutor')]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                validate_tutor(tutor_data(**changes), SimpleNamespace(email='tutor@example.test', intended_name='Synthetic Tutor'))

    def test_role_price_payment_and_category_claims_rejected(self):
        for field in ['registration_basis', 'payment_status', 'fee_ngn', 'eligible', 'category_id', 'adult_declared_on']:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                tutor_data(**{field: 'tutor'})

    def test_invalid_measurements_remain_rejected(self):
        for value in ['0', '-1', 'NaN', 'Infinity', '1.001', 'invalid']:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                tutor_data(height_cm=value)

    def test_tutor_pricing_is_not_a_payment_path(self):
        from .pricing import current_order_prices, PricingConfigurationError
        with self.assertRaises(PricingConfigurationError):
            current_order_prices(SimpleNamespace(registration_basis='tutor'))


class TutorIntegrationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        if connection.vendor != 'postgresql' or not re.fullmatch(r'test_dic_tutor_[0-9]{14}_[a-f0-9]{8}', connection.settings_dict['NAME']):
            raise RuntimeError('Fresh isolated tutor PostgreSQL required.')
        super().setUpClass()

    def setUp(self):
        ContentType.objects.clear_cache()
        self.staff = get_user_model().objects.create_user(username='synthetic-tutor-authorizer', is_staff=True)
        for model, codes in [
            (TutorRegistrationAuthorization, ['can_authorize_dic_tutors']),
            (CampEdition, ['can_view_dic_operations']),
            (CampEnrollment, ['can_manage_dic_ids', 'can_view_dic_ids']),
            (CampCheckIn, ['can_check_in_dic_participants']),
        ]:
            grant_synthetic_permissions(self.staff, model, codes)
        self.staff = get_user_model().objects.get(pk=self.staff.pk)
        self.assertFalse(self.staff.is_superuser)
        self.assertTrue(self.staff.user_permissions.filter(codename='can_authorize_dic_tutors',
            content_type__app_label='dic', content_type__model='tutorregistrationauthorization').exists())
        self.assertTrue(self.staff.has_perm('dic.can_authorize_dic_tutors'))
        today = timezone.localdate()
        self.edition = CampEdition.objects.create(name='SYNTHETIC tutors', year=2097, is_active=True,
            tutor_registration_enabled=True, registration_status='closed', camp_start_date=today + timedelta(days=5),
            camp_end_date=today + timedelta(days=15))
        self.auth = authorize(self.staff, self.edition, 'Synthetic Tutor', 'tutor@example.test', 'Approved synthetic tutor')
        self.token = issue(self.staff, self.auth.pk, 'Initial synthetic invitation')
        self.auth.refresh_from_db()
        self.browser, self.capability = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.verification = TutorVerification.objects.create(authorization=self.auth,
            invitation_digest=self.auth.invitation_digest, browser_digest=digest_value(self.browser), code_digest='',
            capability_digest=digest_value(self.capability), verified_at=timezone.now(), expires_at=timezone.now()+timedelta(minutes=10))

    def _post_teardown(self):
        try:
            super()._post_teardown()  # Preserve deferred-FK checks and rollback.
        finally:
            ContentType.objects.clear_cache()

    def test_rolled_back_content_type_cache_cannot_poison_grants(self):
        # A unique metadata-only probe also works when real model content types
        # already exist. No table, migration, or pre-existing metadata is altered.
        probe = SimpleNamespace()
        probe._meta = SimpleNamespace(app_label='dic', model_name='synthetic_tutor_probe_' + secrets.token_hex(8),
            concrete_model=probe, permissions=[('can_probe_tutor_cache', 'Synthetic cache regression')])
        with transaction.atomic():
            stale = ContentType.objects.get_for_model(probe)
            transaction.set_rollback(True)
        self.assertFalse(ContentType.objects.filter(pk=stale.pk).exists())
        # The manager still holds stale.pk, exactly as it did between tests.
        grant_synthetic_permissions(self.staff, probe, ['can_probe_tutor_cache'])
        permission = self.staff.user_permissions.get(codename='can_probe_tutor_cache')
        self.assertNotEqual(permission.content_type_id, stale.pk)
        self.assertEqual(permission.content_type.model, probe._meta.model_name)
        self.assertTrue(self.staff.has_perm('dic.can_probe_tutor_cache'))
        connection.check_constraints()

    def test_explicit_grant_invalidates_a_cached_permission_denial(self):
        actor = get_user_model().objects.create_user(username='new-synthetic-authorizer', is_staff=True)
        self.assertFalse(actor.has_perm('dic.can_authorize_dic_tutors'))
        grant_synthetic_permissions(actor, TutorRegistrationAuthorization, ['can_authorize_dic_tutors'])
        self.assertTrue(actor.has_perm('dic.can_authorize_dic_tutors'))
        require_authorizer(actor)

    def test_authorized_invitation_creates_username_account_without_email_delivery(self):
        from django.test import override_settings
        from .tutor_registration_api import PATH
        from .models import PortalAccountBooking
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get(PATH+'challenges/').data['csrfToken']
        with override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True, DEBUG=False,
                EMAIL_BACKEND='config.https_email.EmailBackend', RESEND_API_KEY='', DEFAULT_FROM_EMAIL=''), \
                patch('django.core.mail.send_mail', side_effect=AssertionError('No email required')):
            challenge = client.post(PATH+'challenges/', {'invitation': self.token}, format='json', HTTP_X_CSRFTOKEN=csrf)
            self.assertEqual(challenge.status_code, 202)
            self.assertTrue(challenge.data['verified'])
            person = dict(tutor_data())
            for field in ('date_of_birth', 'height_cm', 'weight_kg'):
                if person[field] is not None: person[field] = str(person[field])
            data = {'verification_id': challenge.data['verification_id'], 'participant': person,
                'portal_account': {'username': 'synthetic-tutor', 'password': 'River-Cedar!Sparrow-84',
                    'password_confirmation': 'River-Cedar!Sparrow-84'}}
            created = client.post(PATH+'redeem/', data, format='json', HTTP_X_CSRFTOKEN=csrf)
            self.assertEqual(created.status_code, 200, created.data)
            self.assertEqual(created.data['payment_status'], 'not_required')
            binding = PortalAccountBooking.objects.select_related('account__user').get()
            self.assertTrue(binding.account.user.is_active)
            self.assertFalse(binding.account.user.is_staff)
            self.assertEqual(binding.account.username_key, 'synthetic-tutor')
            csrf = client.get('/api/v1/dic/participant/auth/csrf/').json()['csrfToken']
            signed_in = client.post('/api/v1/dic/participant/auth/password/login/', {
                'identifier': 'synthetic-tutor', 'password': 'River-Cedar!Sparrow-84'}, format='json', HTTP_X_CSRFTOKEN=csrf)
            self.assertEqual(signed_in.status_code, 200, signed_in.data)
            revoke(self.staff, self.auth.pk, 'End tutor access')
            self.assertEqual(client.get('/api/v1/dic/participant/auth/me/').status_code, 403)

    def test_existing_portal_scope_admits_tutor_and_revocation_removes_it(self):
        from .participant_api import scoped_orders
        from .recovery_views import _contact_digest
        order = self.register()
        grant = ParticipantPortalGrant.objects.create(credential_digest=digest_value('portal-synthetic'),
            channel='email', contact_digest=_contact_digest('email', self.auth.email), expires_at=timezone.now()+timedelta(minutes=10))
        ParticipantPortalScope.objects.create(grant=grant, order=order)
        self.assertEqual([row.pk for row in scoped_orders(grant)], [order.pk])
        revoke(self.staff, self.auth.pk, 'End access')
        self.assertEqual(scoped_orders(grant), [])

    def test_tutor_cannot_initialize_payment_or_create_revision(self):
        from rest_framework.test import APIRequestFactory
        from .payment_views import PaymentInitializeView
        from django.core.exceptions import ValidationError as ModelError
        order = self.register()
        with patch('dic.payment_views._order_for_access', return_value=order):
            response = PaymentInitializeView.as_view()(APIRequestFactory().post('/', {}, format='json'), public_id=order.public_id)
        self.assertEqual(response.status_code, 400)
        with self.assertRaises(ModelError): RegistrationOrderPriceRevision(order=order).save()
        with self.assertRaises(ModelError): PaymentAttempt(order=order).save()

    def test_movement_and_controlled_departure_after_revocation(self):
        from uuid import uuid4
        from dic_movement.models import Movement
        from dic_movement.services import scan_arrival, record_movement
        from .identity_tokens import read_token
        grant_synthetic_permissions(self.staff, Movement,
            ['can_view_movements', 'can_record_movements', 'can_authorize_departure'])
        self.register(); enrollment = CampEnrollment.objects.get()
        credential = id_command(enrollment.pk, 'issue', actor=self.staff)
        scan_arrival(self.edition, read_token(credential), self.staff)
        revoke(self.staff, self.auth.pk, 'Ended authorization while inside')
        with self.assertRaises(ValidationError): scan_arrival(self.edition, read_token(credential), self.staff)
        row, created = record_movement(self.edition, enrollment.participant_id, self.staff,
            dict(confirmed=True, action='departure', reason='Supervised departure', authorization_checked=True, authorization_reference='SYNTHETIC supervisor reference', request_id=str(uuid4()), expected_version=0))
        self.assertTrue(created); self.assertEqual(row.kind, 'departure')

    def test_category_activation_and_public_role_claim_are_rejected(self):
        from .serializers import RegistrationOrderCreateSerializer
        from django.core.exceptions import ValidationError as ModelError
        order = self.register(); category = order.items.get().category
        category.is_active = True
        with self.assertRaises(ModelError): category.full_clean()
        raw = camper(registration_basis='tutor')
        serializer = RegistrationOrderCreateSerializer(data={'participants': [raw]})
        self.assertFalse(serializer.is_valid())

    def register(self, **changes):
        return redeem(self.verification.pk, self.browser, self.capability, tutor_data(**changes))

    def test_complimentary_order_outside_public_window_without_payments(self):
        order = self.register()
        self.assertEqual((order.status, order.payment_status, order.registration_basis), ('confirmed', 'not_required', 'tutor'))
        self.assertEqual(order.total_amount_ngn, 0)
        self.assertFalse(PaymentAttempt.objects.exists()); self.assertFalse(RegistrationOrderPriceRevision.objects.exists())
        self.assertFalse(order.items.get().category.is_active)
        self.assertEqual(eligibility(CampEnrollment.objects.get())['code'], 'authorized_tutor')

    def test_seven_day_issue_and_reissue_invalidate_verification(self):
        self.assertEqual(self.auth.expires_at-self.auth.issued_at, timedelta(days=7))
        next_token = issue(self.staff, self.auth.pk, 'Replacement')
        self.assertNotEqual(next_token, self.token)
        with self.assertRaises(ValidationError): self.register()
        self.assertTrue(DICAdminAuditEvent.objects.filter(action='tutor_reissued').exists())

    def test_replay_is_idempotent_but_changed_details_rejected(self):
        first = self.register()
        self.assertEqual(self.register().pk, first.pk)
        self.assertEqual(Participant.objects.count(), 1)
        with self.assertRaises(ValidationError): self.register(address='Changed request')

    def test_wrong_browser_or_unverified_capability_rejected(self):
        with self.assertRaises(ValidationError):
            redeem(self.verification.pk, 'wrong', self.capability, tutor_data())
        self.verification.verified_at = None; self.verification.save()
        with self.assertRaises(ValidationError): self.register()

    def test_expired_invitation_and_disabled_edition_rejected(self):
        TutorRegistrationAuthorization.objects.filter(pk=self.auth.pk).update(expires_at=timezone.now())
        with self.assertRaises(ValidationError): self.register()
        TutorRegistrationAuthorization.objects.filter(pk=self.auth.pk).update(expires_at=timezone.now()+timedelta(days=1))
        self.edition.tutor_registration_enabled=False; self.edition.save()
        with self.assertRaises(ValidationError): self.register()

    def test_revocation_disables_id_portal_and_preserves_arrival(self):
        from .checkin_services import check_in_participant
        from .models import CampCheckIn
        self.register(); enrollment = CampEnrollment.objects.get()
        credential = id_command(enrollment.pk, 'issue', actor=self.staff)
        check_in_participant(self.edition, enrollment.participant_id, self.staff)
        grant = ParticipantPortalGrant.objects.create(credential_digest=digest_value('synthetic-grant'),
            channel='email', contact_digest='synthetic', expires_at=timezone.now()+timedelta(minutes=10))
        scope = ParticipantPortalScope.objects.create(grant=grant, order=enrollment.source_item.order)
        revoke(self.staff, self.auth.pk, 'Synthetic revocation')
        credential.refresh_from_db(); scope.refresh_from_db()
        self.assertIsNotNone(credential.revoked_at); self.assertIsNotNone(scope.revoked_at)
        self.assertFalse(eligibility(enrollment)['eligible']); self.assertTrue(CampCheckIn.objects.exists())

    def test_housing_and_competition_are_excluded(self):
        from .allocation import paid_participants
        from .housing_policy import validate_occupant
        from .activity_scoring_api import camper_scores
        from .portal_dashboard import camper_operations_summary
        from django.core.exceptions import ValidationError as ModelError
        from .models import HousingJob
        order = self.register(); enrollment = CampEnrollment.objects.get()
        self.assertFalse(paid_participants(self.edition).exists())
        with self.assertRaises(ModelError): validate_occupant(enrollment.participant, self.edition, SimpleNamespace())
        with self.assertRaises(ModelError): HousingJob.objects.create(edition=self.edition, participant=enrollment.participant)
        self.assertFalse(camper_scores(order.items.get(), 1)['competitive'])
        self.assertNotIn('house_assignment', camper_operations_summary(enrollment.participant_id, self.edition))

    def test_duplicate_registration_is_not_converted(self):
        Participant.objects.create(adult_declared_on=timezone.localdate(),
            **{k:v for k,v in tutor_data().items() if k != 'category_id'})
        # A person without an edition registration is not proof of a duplicate.
        order = self.register()
        auth2 = authorize(self.staff, self.edition, 'Synthetic Tutor', 'second@example.test', 'Second identity review')
        token2 = issue(self.staff, auth2.pk, 'Second invitation')
        auth2.refresh_from_db()
        row = TutorVerification.objects.create(authorization=auth2, invitation_digest=digest_value(token2),
            browser_digest=digest_value(self.browser), code_digest='', capability_digest=digest_value(self.capability),
            verified_at=timezone.now(), expires_at=timezone.now()+timedelta(minutes=10))
        with self.assertRaises(ValidationError):
            redeem(row.pk, self.browser, self.capability, tutor_data(email='second@example.test'))
        self.assertEqual(order.items.count(), 1)

    def test_reporting_has_no_repricing_or_registration_revenue(self):
        from .operations_api import _order_needs_repricing
        from .operations_exports import registration_export_rows
        order = self.register()
        self.assertFalse(_order_needs_repricing(order))
        headers, rows = registration_export_rows([order])
        self.assertEqual(rows[0][headers.index('Amount (NGN)')], 0)
        self.assertEqual(rows[0][headers.index('Payment verification')], 'not required (complimentary tutor)')

    def test_verification_attempts_commit_and_code_is_single_use(self):
        from .recovery_views import _code_digest
        from .tutor_registration_api import COOKIE, PATH
        self.verification.verified_at = None
        self.verification.code_digest = _code_digest(self.verification.pk, '123456')
        self.verification.save()
        client = APIClient(); client.cookies[COOKIE] = self.browser
        for _ in range(5):
            self.assertEqual(client.post(PATH+'verify/', {'verification_id': str(self.verification.pk), 'code':'000000'}, format='json').status_code, 400)
        self.verification.refresh_from_db(); self.assertEqual(self.verification.attempts, 5)
        self.assertEqual(client.post(PATH+'verify/', {'verification_id': str(self.verification.pk), 'code':'123456'}, format='json').status_code, 400)

    def test_permission_and_csrf_denials(self):
        ordinary = get_user_model().objects.create_user(username='ordinary', is_staff=True)
        with self.assertRaises(PermissionDenied): issue(ordinary, self.auth.pk, 'Denied')
        superuser = get_user_model().objects.create_user(username='undesignated-superuser', is_staff=True, is_superuser=True)
        with self.assertRaises(PermissionDenied): issue(superuser, self.auth.pk, 'No explicit designation')
        self.assertEqual(APIClient(enforce_csrf_checks=True).post('/api/v1/dic/tutor-registration/challenges/', {'invitation': self.token}, format='json').status_code, 403)


def retained_concurrency_check(helper, name, receipt):
    """Dedicated fresh-receipt action: retains committed SYNTHETIC evidence; no flush.

    Ordinary TestCase transactions hide fixtures from other connections. This separate
    opt-in action proves real concurrent redemption without weakening rollback suites.
    """
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import connections
    from .models import RegistrationOrder
    import json
    if not re.fullmatch(r'test_dic_tutor_[0-9]{14}_[a-f0-9]{8}', name):
        raise RuntimeError('Fresh tutor database only.')
    evidence = receipt.with_suffix('.concurrency.json')
    with evidence.open('x', encoding='utf-8') as handle:
        json.dump({'database': name, 'status': 'reserved; retain all partial evidence'}, handle)
    fixture = TutorIntegrationTests('test_replay_is_idempotent_but_changed_details_rejected')
    fixture.setUp()  # Autocommit synthetic fixtures, exclusively in the new receipt DB.
    barrier = Barrier(2, timeout=20)

    def worker():
        try:
            helper.verify_connection_identity(name, connections['default'])
            barrier.wait()
            return str(fixture.register().public_id)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    if (results[0] != results[1] or RegistrationOrder.objects.count() != 1
            or Participant.objects.count() != 1 or CampEnrollment.objects.count() != 1
            or PaymentAttempt.objects.exists() or RegistrationOrderPriceRevision.objects.exists()
            or DICAdminAuditEvent.objects.filter(action='tutor_redeemed').count() != 1):
        raise RuntimeError('Concurrency invariant failed; retain evidence.')
    if not eligibility(CampEnrollment.objects.get())['eligible']:
        raise RuntimeError('Concurrent tutor entitlement failed.')
    from .tutor_validation_evidence import capture, snapshot_digest, validate
    import hashlib
    snapshot = capture(connection)
    completed = {'database': name, 'status': 'PASS; retained synthetic concurrency evidence',
        'order': results[0], 'authorization': str(fixture.auth.pk),
        'creation_receipt_sha256': hashlib.sha256(receipt.read_bytes()).hexdigest(),
        'snapshot_sha256': snapshot_digest(snapshot)}
    validate(snapshot, completed, name, completed['creation_receipt_sha256'])
    evidence.write_text(json.dumps(completed, indent=2), encoding='utf-8')
    print('PASS: two concurrent redemptions, one tutor/order/enrollment/audit. Retain database and receipts; never reuse for rollback suites.')
