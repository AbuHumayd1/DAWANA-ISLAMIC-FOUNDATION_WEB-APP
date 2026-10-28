"""Focused registration privacy checks; integration requires a fresh marked DB."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import re
from types import SimpleNamespace
from uuid import uuid4
from django.core.exceptions import ValidationError as ModelError
from django.db import connection, transaction, IntegrityError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError
from .models import CampEdition, Participant, RegistrationCategory, RegistrationOrder, PaymentAttempt, CampEnrollment, DigitalIDIssue
from .serializers import ParticipantInputSerializer
from .registration_age import validate_declaration, category_age_allowed
from .views import _create_order, _request_fingerprint, _order_summary
from .housing_policy import age_on, age_band, age_reference


def camper(**changes):
    data = dict(category_id=1, full_name='Synthetic privacy camper', address='Synthetic', phone='08012345678',
        email='synthetic@example.test', date_of_birth='2000-01-01', sex='Female', height_cm='170.01', weight_kg='60.01',
        academic_status='Tertiary Student', occupation='None', marital_status='None')
    data.update(changes)
    return data


def payload(**changes):
    data = camper()
    data.update(changes)
    serializer = ParticipantInputSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class RegistrationPrivacyPolicyTests(SimpleTestCase):
    def test_minors_require_exact_dob_and_adults_may_withhold(self):
        today = date(2026, 10, 26)
        validate_declaration('minor', date(2010, 1, 1), today)
        validate_declaration('adult', date(2000, 1, 1), today)
        validate_declaration('adult', None, today)
        for mode, birth in [('minor', None), ('exact', None), ('adult', date(2010, 1, 1)),
                            ('minor', date(2000, 1, 1)), ('exact', date(2027, 1, 1))]:
            with self.subTest(mode=mode, birth=birth), self.assertRaises(ModelError): validate_declaration(mode, birth, today)

    def test_eighteenth_birthday_boundary(self):
        validate_declaration('adult', date(2008, 10, 26), date(2026, 10, 26))
        with self.assertRaises(ModelError): validate_declaration('adult', date(2008, 10, 27), date(2026, 10, 26))

    def test_serializer_optional_measurement_combinations_and_nulls(self):
        for height, weight in [('170.01', '60.01'), ('170.01', None), (None, '60.01'), (None, None),
                               ('', '60.01'), ('170.01', ''), ('', ''), (' ', '\t')]:
            result = payload(age_declaration='adult', date_of_birth=None, height_cm=height, weight_kg=weight)
            for field, value in [('height_cm', height), ('weight_kg', weight)]:
                with self.subTest(field=field, value=value):
                    if value is None or not value.strip():
                        self.assertIsNone(result[field])
                    else:
                        self.assertEqual(result[field], Decimal(value))
        raw = camper(); raw.pop('height_cm'); raw.pop('weight_kg')
        serializer = ParticipantInputSerializer(data=raw); self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data['height_cm'])

    def test_measurements_and_server_audit_override_still_rejected(self):
        for field in ('height_cm', 'weight_kg'):
            for invalid in ('0', '-1', 'NaN', 'Infinity', '0.001', '123456789', 'abc'):
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValidationError): payload(**{field: invalid})
        for changes in [dict(age_declaration='minor', date_of_birth=None), dict(adult_declared_on='2000-01-01'),
                        dict(age_declaration='unknown'), dict(date_of_birth='2999-01-01')]:
            with self.assertRaises(ValidationError): payload(**changes)

    def test_withheld_age_does_not_bypass_category_bounds(self):
        adult = payload(age_declaration='adult', date_of_birth=None)
        for minimum, maximum, expected in [(None, None, True), (18, None, True), (19, None, False), (None, 100, False), (6, 17, False)]:
            self.assertEqual(category_age_allowed(adult, SimpleNamespace(minimum_age=minimum, maximum_age=maximum), timezone.localdate()), expected)

    def test_housing_age_withheld_is_controlled_review_not_fabricated_age(self):
        from .registration_age import asserted_adult
        person = SimpleNamespace(date_of_birth=None, age_declaration='adult')
        edition = SimpleNamespace(year=2026, housing_age_reference_date=date(2026, 12, 23))
        self.assertFalse(asserted_adult(person, edition.housing_age_reference_date))
        person.adult_declared_on = date(2026, 10, 26)
        self.assertTrue(asserted_adult(person, edition.housing_age_reference_date))
        self.assertFalse(asserted_adult(person, date(2026, 10, 25)))
        with self.assertRaises(ModelError):
            age_reference(SimpleNamespace(year=2026, housing_age_reference_date=date(2026, 12, 24)))
        for function in (age_on, age_band):
            with self.assertRaisesMessage(ModelError, 'requires authorized review'): function(person, edition)

    def test_legacy_fingerprint_and_repeat_payload_are_stable(self):
        from django.utils.crypto import salted_hmac
        import json
        old = {'participants': [payload()], 'primary_registrant': {}}
        old['participants'][0].pop('age_declaration')
        expected = salted_hmac('dic.registration-order-request', json.dumps(old, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)).hexdigest()
        self.assertEqual(_request_fingerprint({'participants': [payload()], 'primary_registrant': {}}), expected)
        adult = {'participants': [payload(age_declaration='adult', date_of_birth=None)]}
        self.assertEqual(_request_fingerprint(adult), _request_fingerprint(deepcopy(adult)))

    def test_model_clean_and_null_snapshot_values(self):
        person = Participant(**{key: value for key, value in payload(age_declaration='adult', date_of_birth=None).items() if key != 'category_id'})
        person.clean()
        self.assertEqual(person.adult_declared_on, timezone.localdate())
        self.assertIsNone(person.date_of_birth)

    def test_payment_actor_and_eligibility_override_fields_rejected(self):
        for field in ('payment_status', 'amount_kobo', 'is_staff', 'eligible', 'adult_declared_on'):
            with self.subTest(field=field), self.assertRaises(ValidationError): payload(**{field: 'synthetic'})


@override_settings(DIC_PORTAL_ACCOUNTS_ENABLED=True, DIC_PORTAL_EMAIL_VERIFY_URL='https://example.test/dic/participant')
class RegistrationPrivacyIntegrationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        if connection.vendor != 'postgresql' or not re.fullmatch(r'test_dic_(?:privacy|tutor)_[0-9]{14}_[a-f0-9]{8}', connection.settings_dict['NAME']):
            raise RuntimeError('Fresh isolated privacy PostgreSQL required.')
        super().setUpClass()

    def setUp(self):
        today = timezone.localdate()
        self.edition = CampEdition.objects.create(name='SYNTHETIC Privacy', year=2096, is_active=True,
            camp_start_date=today + timedelta(days=40), camp_end_date=today + timedelta(days=45),
            registration_open_date=today - timedelta(days=1), registration_close_date=today + timedelta(days=1), registration_status='open')
        self.category = RegistrationCategory.objects.create(edition=self.edition, name='Synthetic category', fee_ngn=Decimal('12500.25'))

    def create(self, people):
        request = {'participants': people}
        return _create_order(key_digest=str(uuid4()), fingerprint=_request_fingerprint(request), payload=request)[0]

    def person(self, **changes):
        return payload(category_id=self.category.pk, **changes)

    def test_minor_exact_adult_private_adult_and_all_measurement_combinations(self):
        today = timezone.localdate()
        people = [self.person(age_declaration='minor', date_of_birth=(today - timedelta(days=365 * 10)).isoformat()),
            self.person(age_declaration='adult', height_cm='175', weight_kg=None),
            self.person(age_declaration='adult', date_of_birth=None, height_cm=None, weight_kg='65'),
            self.person(age_declaration='adult', date_of_birth=None, height_cm=None, weight_kg=None)]
        order = self.create(people)
        self.assertEqual(order.items.count(), 4)
        self.assertEqual(order.total_amount_ngn, Decimal('50001.00'))
        rows = list(order.items.select_related('participant').order_by('pk'))
        self.assertEqual(rows[2].participant.adult_declared_on, today)
        self.assertIsNone(rows[2].participant_snapshot['date_of_birth'])
        self.assertIsNone(rows[3].participant_snapshot['height_cm'])
        self.assertIsNone(rows[3].participant_snapshot['weight_kg'])
        self.assertEqual(rows[0].participant_snapshot['height_cm'], '170.01')

    def test_unpaid_adult_has_no_admission_or_qr(self):
        from .participant_services import eligibility, id_command
        order = self.create([self.person(age_declaration='adult', date_of_birth=None, height_cm=None, weight_kg=None)])
        enrollment = CampEnrollment.objects.get(source_item__order=order)
        self.assertFalse(eligibility(enrollment)['eligible'])
        self.assertFalse(DigitalIDIssue.objects.exists()); self.assertFalse(PaymentAttempt.objects.exists())
        actor = SimpleNamespace(is_authenticated=True, is_active=True, is_staff=True, has_perm=lambda _: True)
        with self.assertRaises(ValidationError): id_command(enrollment.pk, 'issue', actor=actor)

    def test_public_api_roundtrip_replay_and_required_minor_dob(self):
        from django.urls import reverse
        raw = camper(); raw.update(category_id=self.category.pk, age_declaration='adult', date_of_birth=None, height_cm=None, weight_kg=None)
        client = APIClient(); key = str(uuid4())
        data = {'primary_registrant': {'full_name': 'Synthetic guardian', 'email': 'guardian@example.test'}, 'participants': [raw],
            'portal_account': {'password': 'River-Cedar!Sparrow-84', 'password_confirmation': 'River-Cedar!Sparrow-84'}}
        response = client.post(reverse('dic:order-create'), data, format='json', HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(response.status_code, 201, response.data)
        replay = client.post(reverse('dic:order-create'), data, format='json', HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(replay.status_code, 200, replay.data); self.assertEqual(RegistrationOrder.objects.count(), 1)
        detail = client.get(reverse('dic:order-detail', args=[response.data['order_id']]), HTTP_AUTHORIZATION='Bearer ' + replay.data['access_token'])
        self.assertEqual(detail.status_code, 200); self.assertIsNone(detail.data['items'][0]['participant_snapshot']['date_of_birth'])
        raw['age_declaration'] = 'minor'
        invalid = client.post(reverse('dic:order-create'), data, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(invalid.status_code, 400); self.assertEqual(RegistrationOrder.objects.count(), 1)

    def test_upper_age_category_rejected_without_partial_booking(self):
        self.category.maximum_age = 30; self.category.save(update_fields=('maximum_age',))
        with self.assertRaises(ValidationError): self.create([self.person(age_declaration='adult', date_of_birth=None)])
        self.assertFalse(RegistrationOrder.objects.exists())

    def test_database_age_constraint_and_positive_measurements(self):
        self.create([self.person()]); person = Participant.objects.get()
        for changes in [dict(date_of_birth=None), dict(height_cm=0), dict(weight_kg=-1), dict(age_declaration='bad')]:
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), transaction.atomic():
                Participant.objects.filter(pk=person.pk).update(**changes)
        Participant.objects.filter(pk=person.pk).update(height_cm=None, weight_kg=None)
        person.refresh_from_db(); self.assertIsNone(person.height_cm); self.assertIsNotNone(person.date_of_birth)

    def test_existing_person_and_snapshot_remain_unchanged_on_another_creation(self):
        first = self.create([self.person()]); before = first.items.get().participant_snapshot
        self.create([self.person(age_declaration='adult', date_of_birth=None)])
        first.refresh_from_db()
        self.assertEqual(first.items.get().participant_snapshot, before)
        self.assertEqual(_order_summary(first, 'synthetic')['total_amount_ngn'], '12500.25')

    def test_private_adult_earlybird_uses_existing_price_snapshot(self):
        self.edition.early_bird_cutoff_at = timezone.now() + timedelta(hours=1)
        self.edition.save(update_fields=('early_bird_cutoff_at',))
        self.category.early_bird_fee_ngn = Decimal('10000.10')
        self.category.save(update_fields=('early_bird_fee_ngn',))
        order = self.create([self.person(age_declaration='adult', date_of_birth=None)])
        self.assertEqual(order.total_amount_ngn, Decimal('10000.10'))
        self.assertEqual(order.current_price_revision.items.get().price_type, 'early_bird')
