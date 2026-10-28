"""Read-only validation of deliberately retained synthetic concurrency evidence.

Not an application entitlement or an invitation. Legacy receipts are checked against
the exact fixture topology; new receipts additionally bind the complete row snapshot.
"""
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
import re

EXPECTED_COUNTS = {
    'accounts_user': 1, 'accounts_user_user_permissions': 5,
    'django_content_type': 4, 'auth_permission': 5,
    'dic_campedition': 1, 'dic_tutorregistrationauthorization': 1,
    'dic_tutorverification': 1, 'dic_registrationcategory': 1,
    'dic_participant': 1, 'dic_primaryregistrant': 1,
    'dic_registrationorder': 1, 'dic_registrationorderitem': 1,
    'dic_campenrollment': 1, 'dic_dicadminauditevent': 4,
}
PERMISSIONS = {
    ('dic', 'tutorregistrationauthorization', 'can_authorize_dic_tutors'),
    ('dic', 'campedition', 'can_view_dic_operations'),
    ('dic', 'campenrollment', 'can_manage_dic_ids'),
    ('dic', 'campenrollment', 'can_view_dic_ids'),
    ('dic', 'campcheckin', 'can_check_in_dic_participants'),
}
STATUS = 'PASS; retained synthetic concurrency evidence'


def require(condition, message):
    if not condition:
        raise RuntimeError('Concurrency evidence rejected: ' + message)


def capture(connection):
    """All public application tables; never emit or persist sensitive row values."""
    snapshot = {}
    with connection.cursor() as cursor:
        for table in sorted(connection.introspection.table_names(cursor)):
            if table == 'django_migrations':
                continue  # The caller independently checks the exact migration set.
            quoted = connection.ops.quote_name(table)
            if table in EXPECTED_COUNTS:
                cursor.execute('SELECT * FROM ' + quoted)
                columns = [column[0] for column in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                # Django's PostgreSQL adapter may leave JSONB as text on raw
                # cursors; ORM JSONField conversion is intentionally bypassed here.
                for row in rows:
                    for field in ('participant_snapshot', 'details'):
                        if isinstance(row.get(field), str):
                            row[field] = json.loads(row[field])
                snapshot[table] = sorted(rows, key=lambda row: str(row['id']))
            else:
                cursor.execute('SELECT count(*) FROM ' + quoted)
                require(cursor.fetchone()[0] == 0, 'unexpected records in ' + table)
                snapshot[table] = []
    return json.loads(json.dumps(snapshot, default=str))


def snapshot_digest(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate(snapshot, evidence, database, creation_digest):
    require(evidence.get('database') == database and evidence.get('status') == STATUS,
            'database or completion status mismatch')
    keys = {'database', 'status', 'order', 'authorization'}
    modern = 'snapshot_sha256' in evidence or 'creation_receipt_sha256' in evidence
    require(set(evidence) == (keys | {'snapshot_sha256', 'creation_receipt_sha256'} if modern else keys),
            'unexpected or incomplete evidence receipt')
    if modern:
        require(evidence['creation_receipt_sha256'] == creation_digest, 'creation receipt mismatch')
        require(evidence['snapshot_sha256'] == snapshot_digest(snapshot), 'retained rows changed')
    for table, count in EXPECTED_COUNTS.items():
        require(len(snapshot.get(table, [])) == count, 'unexpected count in ' + table)
    require(all(not rows for table, rows in snapshot.items() if table not in EXPECTED_COUNTS),
            'unexpected retained table records')

    def one(table):
        return snapshot[table][0]

    user, edition = one('accounts_user'), one('dic_campedition')
    auth, verification = one('dic_tutorregistrationauthorization'), one('dic_tutorverification')
    participant, primary = one('dic_participant'), one('dic_primaryregistrant')
    order, item, enrollment = one('dic_registrationorder'), one('dic_registrationorderitem'), one('dic_campenrollment')
    category = one('dic_registrationcategory')
    require(user['username'] == 'synthetic-tutor-authorizer' and user['is_staff']
            and user['is_active'] and not user['is_superuser'] and user['password'].startswith('!'), 'synthetic authorizer changed')
    ctypes = {row['id']: (row['app_label'], row['model']) for row in snapshot['django_content_type']}
    permissions = {row['id']: (*ctypes.get(row['content_type_id'], ('', '')), row['codename'])
                   for row in snapshot['auth_permission']}
    require(set(permissions.values()) == PERMISSIONS, 'permission ownership or set changed')
    require({(row['user_id'], row['permission_id']) for row in snapshot['accounts_user_user_permissions']}
            == {(user['id'], pk) for pk in permissions}, 'explicit permission grants changed')
    require(edition['name'] == 'SYNTHETIC tutors' and edition['year'] == 2097
            and edition['tutor_registration_enabled'] and edition['is_active']
            and edition['registration_status'] == 'closed', 'synthetic edition changed')
    require(str(auth['id']) == evidence['authorization'] and str(order['public_id']) == evidence['order'], 'record IDs mismatch')
    require(auth['edition_id'] == edition['id'] == order['edition_id'] == category['edition_id'] == enrollment['edition_id'], 'edition links mismatch')
    require(auth['authorized_by_id'] == user['id'] and auth['enrollment_id'] == enrollment['id']
            and not auth['revoked_at'] and not auth['revoked_by_id'] and not auth['revocation_reason'], 'authorization links/state changed')
    require(auth['intended_name'] == participant['full_name'] == primary['full_name'] == 'Synthetic Tutor'
            and auth['email'] == participant['email'] == primary['email'] == 'tutor@example.test'
            and primary['phone'] == participant['phone']
            and auth['reason'] == 'Approved synthetic tutor', 'authorized identity changed')
    require(order['registration_basis'] == 'tutor' and order['status'] == 'confirmed'
            and order['payment_status'] == 'not_required' and order['current_price_revision_id'] is None
            and order['access_token_revoked_at'] is None and order['primary_registrant_id'] == primary['id'], 'complimentary order changed')
    require(item['order_id'] == order['id'] and item['participant_id'] == participant['id']
            and item['category_id'] == category['id'] and enrollment['participant_id'] == participant['id']
            and enrollment['source_item_id'] == item['id'] and not enrollment['restriction_reason']
            and not enrollment['source_review_fingerprint'], 'registration source links changed')
    require(category['name'] == item['category_name_snapshot'] == 'DIC Tutor' and not category['is_active']
            and Decimal(category['fee_ngn']) == Decimal(item['fee_snapshot_ngn']) == 0, 'category or amount changed')
    require(participant['age_declaration'] == 'adult' and participant['date_of_birth'] is None
            and participant['adult_declared_on'] is not None
            and participant['height_cm'] is None and participant['weight_kg'] is None, 'privacy evidence changed')
    require({key: participant[key] for key in ('address', 'phone', 'sex', 'academic_status', 'occupation', 'marital_status')}
            == dict(address='Synthetic', phone='08012345678', sex='Female', academic_status='Tertiary Student',
                    occupation='None', marital_status='None'), 'synthetic participant fields changed')
    require(verification['authorization_id'] == auth['id'] and verification['verified_at'] == auth['verified_at']
            and verification['invitation_digest'] == auth['invitation_digest']
            and verification['request_fingerprint'] == order['request_fingerprint']
            and verification['code_digest'] == '', 'verified redemption evidence changed')
    for value in [auth['invitation_digest'], verification['browser_digest'], verification['capability_digest'], order['request_fingerprint']]:
        require(bool(re.fullmatch(r'[a-f0-9]{64}', value)), 'invalid credential/fingerprint digest')
    issued, expiry, redeemed = (datetime.fromisoformat(auth[key]) for key in ('issued_at', 'expires_at', 'redeemed_at'))
    require(expiry - issued == timedelta(days=7) and issued <= redeemed < expiry
            and datetime.fromisoformat(auth['authorized_at']) <= issued
            and datetime.fromisoformat(auth['verified_at']) <= redeemed, 'authorization chronology changed')
    require(item['participant_snapshot'] == {key: participant[key] for key in (
        'full_name', 'address', 'phone', 'email', 'date_of_birth', 'sex', 'height_cm', 'weight_kg',
        'academic_status', 'occupation', 'marital_status', 'age_declaration', 'adult_declared_on')}, 'participant snapshot mismatch')
    events = {row['action']: row for row in snapshot['dic_dicadminauditevent']}
    require(set(events) == {'tutor_authorized', 'tutor_issued', 'tutor_redeemed', 'participant_enrollment_created'}, 'audit action set changed')
    for action in ('tutor_authorized', 'tutor_issued', 'tutor_redeemed'):
        event = events[action]
        require(event['target_type'] == 'TutorRegistrationAuthorization' and event['target_id'] == str(auth['id'])
                and event['actor_id'] == (None if action == 'tutor_redeemed' else user['id']), 'audit identity changed')
    require(events['tutor_redeemed']['details'] == {'order': str(order['public_id']), 'enrollment': str(enrollment['id'])}, 'redemption audit mismatch')
    require(events['tutor_authorized']['details'] == {'reason': auth['reason']}, 'authorization audit reason changed')
    issued_details = events['tutor_issued']['details']
    require(set(issued_details) == {'reason', 'previous_digest', 'expires_at'}
            and issued_details['reason'] == 'Initial synthetic invitation' and issued_details['previous_digest'] is None
            and datetime.fromisoformat(issued_details['expires_at']) == expiry, 'invitation audit changed')
    event = events['participant_enrollment_created']
    require(event['target_type'] == 'CampEnrollment' and event['target_id'] == str(enrollment['id'])
            and event['actor_id'] is None and event['details'] == {}, 'enrollment audit mismatch')
    return 'bound snapshot' if modern else 'legacy receipt with exact fixture checks'
