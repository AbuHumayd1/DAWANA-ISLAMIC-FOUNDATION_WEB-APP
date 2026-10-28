"""Explicit local-only OTP fixture actions. Never targets dawana_dev or migrates on startup."""
import argparse
import hashlib
import os
from pathlib import Path
import sys
from datetime import date
from decimal import Decimal
from getpass import getpass

ROOT = Path(__file__).resolve().parents[1]
DATABASE = 'test_dic_portal_2026_local'
TARGET = ('dic', '0026_house_score_transaction')
MARKER = hashlib.sha256(b'dawana-isolated-portal-unpaid-fixture-v1').hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def configure():
    sys.path.insert(0, str(ROOT / 'backend'))
    import environ
    environ.Env.read_env(ROOT / 'backend' / '.env')
    env = environ.Env()
    source = env.db_url('DATABASE_URL') if env('DATABASE_URL', default='') else dict(
        ENGINE='django.db.backends.postgresql', HOST=env('DB_HOST', default='127.0.0.1'),
        PORT=env('DB_PORT', default='5432'), USER=env('DB_USER'), PASSWORD=env('DB_PASSWORD', default=''))
    require(source['ENGINE'] == 'django.db.backends.postgresql', 'PostgreSQL is required.')
    require(source.get('HOST') in ('localhost', '127.0.0.1', '::1'), 'Only loopback PostgreSQL is allowed.')
    require(os.environ.get('DJANGO_SETTINGS_MODULE', 'config.settings.development') == 'config.settings.development',
        'Refusing non-development settings.')
    os.environ.update(DATABASE_URL='', DB_NAME=DATABASE, DB_HOST=source['HOST'],
        DB_PORT=str(source.get('PORT') or 5432), DB_USER=source['USER'], DB_PASSWORD=source.get('PASSWORD') or '',
        DB_TEST_NAME='test_dic_portal_2026_runner', DJANGO_SETTINGS_MODULE='config.settings.development')
    import django
    django.setup()
    from django.conf import settings
    require(settings.DEBUG and settings.SETTINGS_MODULE == 'config.settings.development', 'Development only.')
    require(settings.DATABASES['default']['NAME'] == DATABASE, 'Unexpected database; refusing execution.')
    return source


def migration_plan():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan([TARGET])
    require(not any(backwards for migration, backwards in plan), 'Refusing migration rollback.')
    require(('dic', '0027_feedback_welfare') not in executor.loader.applied_migrations,
        '0027 is already applied; this is not the expected isolated database.')
    require(all(migration.app_label != 'dic' or migration.name <= TARGET[1] for migration, _ in plan),
        'Plan includes an unapproved DIC migration.')
    require(all(migration.app_label != 'dic_scoring' for migration, _ in plan), 'Scoring schema is unnecessary for this unpaid OTP fixture.')
    for migration, _ in plan:
        print(f'  {migration.app_label}.{migration.name}')
    if not plan:
        print('  No pending migrations to the approved target.')
    return executor, plan


def seed():
    from django.core.validators import validate_email
    from django.db import connection, transaction
    from dic.models import (CampEdition, RegistrationCategory, PrimaryRegistrant, Participant,
        RegistrationOrder, RegistrationOrderItem, PaymentAttempt, CampCheckIn, CampEnrollment,
        DigitalIDIssue, HouseAllocation, HouseScoreTransaction)
    from dic.security import digest_value
    import secrets
    email = os.environ.get('DIC_PORTAL_TEST_EMAIL') or getpass('Authorised test email (hidden): ')
    validate_email(email)
    email = email.strip().lower()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [2026102601])
        existing = RegistrationOrder.objects.filter(idempotency_key_digest=MARKER).first()
        require(not any(model.objects.exists() for model in (PaymentAttempt, CampCheckIn,
            CampEnrollment, DigitalIDIssue, HouseAllocation, HouseScoreTransaction)),
            'Payment, ID, check-in, housing or scoring data exists; refusing this minimal fixture.')
        if existing:
            require(RegistrationOrder.objects.count() == 1 and Participant.objects.count() == 1
                and RegistrationOrderItem.objects.count() == 1, 'Unexpected fixture inventory.')
            require(existing.status == 'submitted' and existing.payment_status == 'pending'
                and existing.access_token_revoked_at is None and existing.items.count() == 1
                and existing.primary_registrant.email == email, 'Fixture changed; refusing to overwrite it.')
            require(existing.edition.registration_status == 'draft'
                and existing.edition.registration_open_date is None and existing.edition.registration_close_date is None,
                'Edition changed; refusing to proceed.')
            item = existing.items.get()
            require(not item.category.is_active and item.category.fee_ngn is None
                and item.category.early_bird_fee_ngn is None and item.fee_snapshot_ngn == 0,
                'Fixture category or snapshot changed; refusing to proceed.')
            print('Existing unpaid fixture retained. Booking reference: ' + str(existing.public_id))
            return
        require(not any(model.objects.exists() for model in (CampEdition, RegistrationCategory,
            PrimaryRegistrant, Participant, RegistrationOrder, RegistrationOrderItem)), 'Refusing to seed a nonempty database.')
        edition = CampEdition.objects.create(name='SYNTHETIC LOCAL OTP TEST — DIC 2026', year=2026,
            camp_start_date=date(2026, 12, 23), camp_end_date=date(2027, 1, 1),
            registration_status='draft', is_active=True)
        category = RegistrationCategory.objects.create(edition=edition, name='LOCAL OTP FIXTURE — NOT A REGISTRATION OFFER',
            is_active=False, fee_ngn=None, description='Required relation only. No approved price or payable quote.')
        primary = PrimaryRegistrant.objects.create(full_name='SYNTHETIC LOCAL TEST BOOKER', email=email)
        camper = Participant.objects.create(full_name='SYNTHETIC LOCAL TEST CAMPER', address='Synthetic test record',
            phone='00000000000', email=email, date_of_birth=date(2000, 1, 1), sex='Male',
            height_cm=Decimal('170'), weight_kg=Decimal('65'), academic_status='Not Currently in School',
            occupation='None', marital_status='None')
        # public_id uses the application's existing UUID default. No usable bearer is exposed.
        order = RegistrationOrder.objects.create(edition=edition, primary_registrant=primary,
            status='submitted', payment_status='pending', idempotency_key_digest=MARKER,
            request_fingerprint=MARKER, access_token_digest=digest_value(secrets.token_urlsafe(32)))
        RegistrationOrderItem.objects.create(order=order, participant=camper, category=category,
            fee_snapshot_ngn=Decimal('0'), participant_snapshot={})
        print('Created one pending/unpaid booking and one camper. Booking reference: ' + str(order.public_id))
        print('Zero snapshot is not a payable quote. No payment, enrollment, check-in, ID or scoring records created.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create-db', 'plan', 'migrate', 'seed', 'serve', 'worker'))
    parser.add_argument('--confirm-database', default='')
    args = parser.parse_args()
    source = configure()
    print('Development-only database: ' + DATABASE)
    if args.action in ('create-db', 'migrate', 'seed', 'worker'):
        require(args.confirm_database == DATABASE, 'Explicit --confirm-database is required for this action.')
    if args.action == 'create-db':
        import psycopg
        from psycopg import sql
        with psycopg.connect(host=source['HOST'], port=source.get('PORT') or 5432,
                user=source['USER'], password=source.get('PASSWORD') or '', dbname='postgres',
                autocommit=True, connect_timeout=5) as conn:
            require(not conn.execute('SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=%s)', [DATABASE]).fetchone()[0],
                'Database already exists; refusing reuse/overwrite during creation. Use plan to inspect it.')
            conn.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(DATABASE)))
        print('Created isolated empty database. No schema or fixture inserted.')
        return
    executor, plan = migration_plan()
    if args.action == 'plan':
        return
    if args.action == 'migrate':
        executor.migrate([TARGET], plan=plan)
        print('Targeted schema applied only to isolated database; 0027 excluded.')
        return
    require(not plan, 'Apply the reviewed targeted isolated migration plan first.')
    if args.action == 'seed':
        seed()
    else:
        from django.core.management import call_command
        if args.action == 'serve':
            call_command('runserver', '127.0.0.1:8000', use_reloader=False)
        else:
            call_command('send_dic_portal_messages', limit=50)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Settings/provider/database exceptions can contain credentials; never echo them.
        print('STOP: ' + (str(error) if type(error) is RuntimeError else type(error).__name__ + '; private details suppressed.'), file=sys.stderr)
        sys.exit(1)
