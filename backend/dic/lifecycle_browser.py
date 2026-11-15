"""Explicit real browser + disposable Django endpoint lifecycle acceptance."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest import skipUnless
from django.test import LiveServerTestCase, override_settings
from .test_operations_lifecycle import LifecycleFixture


@skipUnless(os.environ.get('DIC_LIFECYCLE_BROWSER_CHECK') == '1', 'Explicit local browser acceptance only')
@override_settings(CSRF_TRUSTED_ORIGINS=['http://127.0.0.1:5178'])
class LifecycleBrowserTests(LifecycleFixture, LiveServerTestCase):
    host='127.0.0.1'

    def test_all_operations_pages_and_lifecycle_actions(self):
        env={**os.environ,'OWNER_TEST_API':self.live_server_url,
            'OWNER_TEST_SESSION':self.client.cookies['sessionid'].value,
            'LIFECYCLE_EDITION':str(self.edition.pk),
            'LIFECYCLE_RECORDS':json.dumps({'unpaid':str(self.deleted_unpaid.public_id),
                'paid':str(self.deleted_paid.public_id),'archived':str(self.archived.public_id)})}
        result=subprocess.run(['node','scripts/check-operations-lifecycle.cjs'],
            cwd=Path(__file__).resolve().parents[2]/'dawana-platform',env=env,
            stdout=sys.stdout,stderr=sys.stderr,text=True,timeout=240)
        self.assertEqual(result.returncode,0)
        self.assertEqual(self.get('operations-finance')['summary']['net_position_kobo'],400000)
