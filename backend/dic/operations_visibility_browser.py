"""Opt-in real browser acceptance against a disposable Django LiveServer."""
import json
import os
import sys
from pathlib import Path
import subprocess
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase, override_settings
from .test_operations_portal import DICOperationsPortalTests as Fixtures


@skipUnless(os.environ.get('DIC_VISIBILITY_BROWSER_CHECK') == '1', 'Explicit local browser acceptance only')
@override_settings(CSRF_TRUSTED_ORIGINS=['http://127.0.0.1:5178'])
class OperationsVisibilityBrowserTests(LiveServerTestCase):
    host = '127.0.0.1'
    setUp = Fixtures.setUp
    create_user = Fixtures.create_user
    make_order = Fixtures.make_order

    def test_real_browser_counts_lists_and_lifecycle(self):
        actor = get_user_model().objects.create_superuser('browser-visibility', 'owner@example.test', 'synthetic')
        self.client.force_login(actor)
        env = {**os.environ, 'OWNER_TEST_API': self.live_server_url,
            'OWNER_TEST_SESSION': self.client.cookies['sessionid'].value,
            'OWNER_TEST_RECORDS': json.dumps([
                {'id': str(self.unpaid_order.public_id), 'participants': 1},
                {'id': str(self.paid_order.public_id), 'participants': 2}])}
        result = subprocess.run(['node', 'scripts/check-operations-visibility.cjs'],
            cwd=Path(__file__).resolve().parents[2] / 'dawana-platform', env=env,
            text=True, stdout=sys.stdout, stderr=sys.stderr, timeout=120)
        self.assertEqual(result.returncode, 0)
