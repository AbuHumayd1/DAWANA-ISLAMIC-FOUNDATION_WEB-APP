"""Isolated local ID demo. Never seeds/migrates the real development database."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import uuid
from local_preview import configure, setup, require, StopPreview, STATE


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'serve'])
    args = parser.parse_args()
    target = configure()
    import qrcode  # Fail before database creation if the new dependency is absent.
    saved = STATE / 'id-demo.json'
    if args.mode == 'prepare':
        password = getpass.getpass('Choose a LOCAL DEMO Admin password (hidden; never saved in files): ')
        require(len(password) >= 12, 'Use at least 12 characters for the local demonstration account.')
        import psycopg
        from psycopg import sql
        name = 'dawana_ids_demo_' + uuid.uuid4().hex
        with psycopg.connect(host=target['host'], port=target['port'], user=target['user'], password=target['password'],
                             dbname='postgres', autocommit=True, connect_timeout=5) as conn:
            require(not conn.execute('SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=%s)', (name,)).fetchone()[0],
                    'Generated demo database already exists; refusing reuse.')
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        target['name'] = name
    else:
        require(saved.is_file(), 'Prepare the isolated ID demo first.')
        manifest = json.loads(saved.read_text(encoding='utf-8'))
        require(manifest['host'] == target['host'] and manifest['port'] == target['port'], 'Local server changed since demonstration preparation.')
        target['name'] = manifest['name']
    require(re.fullmatch(r'dawana_ids_demo_[0-9a-f]{32}', target['name']), 'Refusing a non-isolated demonstration database.')
    os.environ.update(DB_NAME=target['name'], DATABASE_URL='', PAYSTACK_SECRET_KEY='', AWS_EC2_METADATA_DISABLED='true')
    setup(target)
    from django.conf import settings
    settings.DIC_MEMORY_LOCAL_ROOT = STATE / 'id-demo-media' / target['name']
    from django.core.management import call_command
    if args.mode == 'prepare':
        call_command('migrate', interactive=False, verbosity=1)
        call_command('check', verbosity=0)
        from dic.identity_demo_data import seed_demo
        cards = seed_demo(password)
        del password
        STATE.mkdir(exist_ok=True)
        manifest = {key: target[key] for key in ('host', 'port', 'name')}
        manifest['cards'] = cards
        text = json.dumps(manifest, indent=2)
        # Retain a manifest per demo; no database or previous recovery file is removed.
        (STATE / (target['name'] + '.json')).write_text(text, encoding='utf-8')
        saved.write_text(text, encoding='utf-8')
        print('Isolated SYNTHETIC demonstration database: ' + target['name'])
        print('Local Admin account: local-id-demo (use the password entered in this console).')
        print('Participant directory: http://127.0.0.1:8000/admin/dic/campenrollment/')
        for card in cards:
            print('Actual demo card: http://127.0.0.1:8000/api/v1/dic/ids/cards/' + card + '/')
    else:
        from django.contrib import admin
        admin.site.site_header = 'DAWANA — SYNTHETIC LOCAL ID DEMONSTRATION'
        call_command('runserver', '127.0.0.1:8000', use_reloader=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        import sys
        message = str(error) if isinstance(error, StopPreview) else type(error).__name__ + ': local ID demo prerequisite failed; credentials suppressed.'
        print('STOP: ' + message, file=sys.stderr)
        sys.exit(1)
