"""Phase 5 supersedes postponement; authenticated access is mandatory."""
from unittest.mock import patch
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory
from .feedback_api import CamperWelfareSubmitView

class WelfarePostponementTests(SimpleTestCase):
    def test_reactivated_route_requires_session(self):
        with patch('dic.feedback_api.require_feedback_storage') as storage:
            response=CamperWelfareSubmitView.as_view()(APIRequestFactory().get('/?item_id=1'))
        self.assertIn(response.status_code,(401,403))
        storage.assert_not_called()
