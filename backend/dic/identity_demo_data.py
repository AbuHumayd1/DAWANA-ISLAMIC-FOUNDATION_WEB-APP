"""Synthetic records, callable only in a fresh isolated local demonstration DB."""
import hashlib
import uuid
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone


@transaction.atomic
def seed_demo(password):
    from .models import (CampEdition, Participant, PrimaryRegistrant, RegistrationCategory,
        RegistrationOrder, RegistrationOrderItem, PaymentAttempt, House, GuardianRelationship)
    from .pricing import create_price_revision, current_order_prices
    from .participant_services import ensure_enrollment
    from .identity_cards import command
    from .housing_service import review_guardian
    from .allocation import assign_participant
    name = connection.settings_dict['NAME']
    if (settings.SETTINGS_MODULE != 'config.settings.development' or not settings.DEBUG
            or not name.startswith('dawana_ids_demo_') or connection.settings_dict.get('HOST') not in ('127.0.0.1', 'localhost', '::1')):
        raise RuntimeError('Synthetic data requires an isolated local ID demonstration database.')
    if CampEdition.objects.exists() or Participant.objects.exists() or get_user_model().objects.exists():
        raise RuntimeError('Refusing to seed a nonempty database.')
    actor = get_user_model().objects.create_superuser(username='local-id-demo', email='id-demo@example.invalid', password=password)
    edition = CampEdition.objects.create(name='SYNTHETIC DEMO — DIC 2026', year=2026,
        camp_start_date=date(2026, 12, 23), camp_end_date=date(2027, 1, 1),
        housing_age_reference_date=date(2026, 12, 23), is_active=True)
    category = RegistrationCategory.objects.create(edition=edition, name='SYNTHETIC DEMO CATEGORY', fee_ngn=Decimal('100.00'))
    registrant = PrimaryRegistrant.objects.create(full_name='SYNTHETIC DEMO BOOKER', email='demo@example.invalid')
    random_hash = lambda: hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    order = RegistrationOrder.objects.create(edition=edition, primary_registrant=registrant,
        status='confirmed', payment_status='paid', idempotency_key_digest=random_hash(),
        request_fingerprint=random_hash(), access_token_digest=random_hash())
    people = []
    for label, sex, birth in [('SYNTHETIC — Amina Demo', 'Female', date(1995, 1, 1)),
                              ('SYNTHETIC — Child Demo', 'Male', date(2022, 1, 1)),
                              ('SYNTHETIC — Yusuf Demo', 'Male', date(1990, 1, 1))]:
        participant = Participant.objects.create(full_name=label, address='SYNTHETIC — no real address',
            phone='00000000000', email=f'{uuid.uuid4()}@example.invalid', date_of_birth=birth, sex=sex,
            height_cm=Decimal('100.00'), weight_kg=Decimal('30.00'),
            academic_status=Participant.AcademicStatus.SECONDARY, occupation=Participant.Occupation.NOT_APPLICABLE,
            marital_status=Participant.MaritalStatus.NOT_APPLICABLE)
        item = RegistrationOrderItem.objects.create(order=order, participant=participant, category=category,
            category_name_snapshot=category.name, fee_snapshot_ngn=category.fee_ngn,
            participant_snapshot={'full_name': label})
        people.append((participant, item))
    revision = create_price_revision(order, current_order_prices(order), accepted_at=timezone.now())
    amount = int(order.total_amount_ngn * 100)
    PaymentAttempt.objects.create(order=order, reference='SYNTHETIC-DEMO-' + uuid.uuid4().hex,
        amount_kobo=amount, currency='NGN', status='successful', price_revision=revision,
        provider_status='success', provider_reported_amount_kobo=amount, provider_reported_currency='NGN',
        provider_transaction_id='SYNTHETIC-DEMO-' + uuid.uuid4().hex, provider_paid_at=timezone.now(), verified_at=timezone.now())
    guardian, child = people[0][0], people[1][0]
    relation = GuardianRelationship.objects.create(edition=edition, child=child, guardian=guardian,
        reason='SYNTHETIC demonstration relationship, not a real guardianship.')
    review_guardian(relation.pk, actor, 'approved', 'SYNTHETIC isolated demonstration approval.')
    house = House.objects.create(edition=edition, name='SYNTHETIC DEMO FEMALE HOUSE', gender='female', capacity=25)
    assign_participant(guardian.pk, edition.pk, house.pk, actor, reason='SYNTHETIC isolated demo group assignment.')
    # Automation remains disabled; no actual operational inventory is created.
    enrollments = []
    for participant, item in people:
        enrollment = ensure_enrollment(item.pk)
        command(enrollment, 'issue', actor, 'SYNTHETIC local demonstration issuance.')
        enrollments.append(str(enrollment.pk))
    return enrollments
