"""Exact ages and explicit adult assertions; never substitute a birth date."""
from django.core.exceptions import ValidationError
from datetime import date


def validate_guardian_contact(participants, contact):
    """The existing booking contact is the declared guardian for under-16s.

    This does not create housing guardianship or account ownership evidence.
    Existing contacts are never rewritten by this input-only validation.
    """
    from rest_framework.exceptions import ValidationError as InputError
    reference = date(2026, 12, 23)
    if any(person.get('date_of_birth') and exact_age(person['date_of_birth'], reference) < 16
           for person in participants):
        phone = contact.get('phone', '').strip()
        if not 7 <= sum(char.isdigit() for char in phone) <= 15:
            raise InputError({'primary_registrant': {'phone': 'Enter a valid parent or guardian phone number for participants below 16.'}})


def exact_age(birth, reference):
    if birth is None or birth > reference:
        raise ValidationError('An applicable exact date of birth is required.')
    return reference.year - birth.year - ((reference.month, reference.day) < (birth.month, birth.day))


def validate_declaration(declaration, birth, reference):
    if declaration not in ('exact', 'minor', 'adult'):
        raise ValidationError('Choose a valid age declaration.')
    if birth is None:
        if declaration != 'adult':
            raise ValidationError('Date of birth is required for minors and exact-date registration.')
        return
    age = exact_age(birth, reference)
    if declaration == 'adult' and age < 18:
        raise ValidationError('Adult registration requires age 18 or older.')
    if declaration == 'minor' and age >= 18:
        raise ValidationError('Select adult registration for campers aged 18 or older.')


def asserted_adult(participant, reference):
    """A declaration is self-reported, not documentary age verification."""
    return (participant.date_of_birth is None
        and getattr(participant, 'age_declaration', None) == 'adult'
        and getattr(participant, 'adult_declared_on', None) is not None
        and participant.adult_declared_on <= reference)


def category_age_allowed(data, category, reference):
    birth = data.get('date_of_birth')
    validate_declaration(data.get('age_declaration', 'exact'), birth, reference)
    # Explicit payment classification is independent of safeguarding and housing.
    kind = getattr(category, 'payment_kind', '')
    if kind:
        from .models import Participant
        status = data.get('academic_status')
        graduate = status == Participant.AcademicStatus.GRADUATE
        undergraduate = status == Participant.AcademicStatus.TERTIARY
        age = exact_age(birth, reference) if birth else None
        if kind == 'graduate_adult':
            return graduate or (age is not None and age > 30) or (
                not undergraduate and (age is None or age >= 17)
            )
        if kind == 'undergraduate':
            return undergraduate and age is not None and 17 <= age <= 30
        # Younger graduates retain the agreed graduate payment classification.
        if graduate or age is None:
            return False
        bounds = {'pre_primary': (0, 5), 'primary': (6, 10), 'secondary': (11, 16)}
        if kind not in bounds:
            return False
        minimum, maximum = bounds[kind]
        return minimum <= age <= maximum
    if birth is None:
        # 18+ alone cannot prove a finite upper limit or a minimum above 18.
        return (category.minimum_age is None or category.minimum_age <= 18) and category.maximum_age is None
    age = exact_age(birth, reference)
    return (category.minimum_age is None or age >= category.minimum_age) and (category.maximum_age is None or age <= category.maximum_age)
