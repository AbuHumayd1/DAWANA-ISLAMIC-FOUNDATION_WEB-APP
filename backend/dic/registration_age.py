"""Exact ages and explicit adult assertions; never substitute a birth date."""
from django.core.exceptions import ValidationError


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
    if birth is None:
        # 18+ alone cannot prove a finite upper limit or a minimum above 18.
        return (category.minimum_age is None or category.minimum_age <= 18) and category.maximum_age is None
    age = exact_age(birth, reference)
    return (category.minimum_age is None or age >= category.minimum_age) and (category.maximum_age is None or age <= category.maximum_age)
