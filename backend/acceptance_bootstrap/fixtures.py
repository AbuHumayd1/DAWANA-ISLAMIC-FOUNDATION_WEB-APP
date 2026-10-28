"""Deterministic symbolic fixture recipes, not a database loader or dump."""
import copy
from .config import require

CATALOG = {
    'edition': {'key': 'acceptance_camp', 'start': '2026-12-23', 'end': '2027-01-01'},
    'people': [
        {'key': 'adult', 'name': 'Synthetic Adult', 'email': 'adult@example.test', 'age_band': 'adult'},
        {'key': 'guardian', 'name': 'Synthetic Guardian', 'email': 'guardian@example.test', 'age_band': 'adult'},
        {'key': 'minor_a', 'name': 'Synthetic Minor A', 'email': 'minor_a@example.test', 'date_of_birth': '2014-01-01', 'guardian': 'guardian'},
        {'key': 'minor_b', 'name': 'Synthetic Minor B', 'email': 'minor_b@example.test', 'date_of_birth': '2016-01-01', 'guardian': 'guardian'},
        {'key': 'unrelated', 'name': 'Synthetic Unrelated', 'email': 'unrelated@example.test', 'age_band': 'adult'},
    ],
    'category_recipes': [{'key': 'adult_category', 'synthetic_price_ngn': '1000.00'},
                         {'key': 'minor_category', 'synthetic_price_ngn': '500.00'}],
    'house_assignments': [{'person': 'adult', 'house': 'Synthetic House A'}, {'person': 'minor_a', 'house': 'Synthetic House B'}],
    'accounts': [
        {'key': 'officer', 'email': 'officer@example.test', 'permissions': ['dic.can_view_dic_operations', 'dic.can_view_dic_ids', 'dic.can_check_in_dic_participants']},
        {'key': 'administrator', 'email': 'administrator@example.test', 'permissions': ['dic.can_view_dic_operations', 'dic.view_participant']},
        {'key': 'finance', 'email': 'finance@example.test', 'permissions': ['dic.can_view_dic_operations', 'dic.can_view_dic_finance', 'dic_finance.can_reconcile_finance', 'dic_finance.can_export_finance']},
        {'key': 'welfare', 'email': 'welfare@example.test', 'permissions': ['dic.can_view_dic_operations', 'dic.can_view_dic_welfare', 'dic.can_manage_dic_welfare']},
    ],
    'bookings': [{'key': 'single', 'people': ['adult'], 'payer': 'adult', 'category_keys': ['adult_category']},
                 {'key': 'grouped', 'people': ['minor_a', 'minor_b'], 'payer': 'guardian', 'category_keys': ['minor_category', 'minor_category']}],
    'qr_cases': ['valid', 'invalid', 'expired', 'revoked', 'duplicate', 'unauthorized_officer'],
    'payment_cases': ['success', 'failed', 'pending', 'abandoned', 'wrong_amount', 'duplicate_callback', 'duplicate_webhook', 'grouped'],
    'feedback': [{'person': 'adult', 'description': 'Synthetic feedback for acceptance only.'}],
    'welfare': [{'person': 'minor_a', 'reporter': 'guardian', 'description': 'Synthetic confidential welfare example.', 'internal_note': 'Synthetic officer-only note.'}],
    'reconciliation': [{'booking': 'grouped', 'outcome': 'matched', 'evidence': 'Synthetic mock payment evidence only.'}],
    'timetables': [
        {'type': 'activities', 'date': '2026-12-23', 'description': 'Synthetic acceptance activity', 'status': 'draft'},
        {'type': 'food', 'date': '2026-12-23', 'description': 'Synthetic acceptance meal', 'status': 'published'},
    ],
    'academic_classes': [],
    'unsupported': ['academic_class_assignment', 'portal_announcements'],
}


def fixture_definitions():
    return copy.deepcopy(CATALOG)


def validate_fixtures(data):
    require(set(data) == set(CATALOG), 'Fixture recipe schema rejected.')
    require(data['edition'] == CATALOG['edition'], 'Synthetic edition recipe rejected.')
    people = data['people']; ids = {p['key'] for p in people}
    require(len(ids) == len(people) and ids == {p['key'] for p in CATALOG['people']}, 'Fixture people identifiers rejected.')
    for person in people + data['accounts']:
        require(person['email'].endswith('@example.test'), 'Real fixture contact rejected.')
        require(not person.get('phone') and not person.get('password') and not person.get('is_superuser'), 'Unsafe fixture contact/credential/privilege rejected.')
    for person in people:
        require(person.get('guardian', 'guardian') in ids and person.get('name', '').startswith('Synthetic '), 'Synthetic person relationship rejected.')
    require(data['academic_classes'] == [], 'Unsupported academic class fixtures rejected.')
    for recipe in data['bookings']:
        require(set(recipe['people']).issubset(ids) and recipe['payer'] in ids, 'Fixture booking references rejected.')
    require(len(data['timetables']) == 2 and {r['type'] for r in data['timetables']} == {'activities', 'food'}
            and all(r['description'].startswith('Synthetic acceptance ') for r in data['timetables']), 'Synthetic timetable recipe rejected.')
    # Recipes are intentionally immutable reviewed definitions. No arbitrary real
    # addresses, role grants, source timetable data or API payloads can be added.
    require(data == CATALOG, 'Fixture definitions differ from reviewed synthetic recipes.')
    return True
