from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles import finders
from django.test import TestCase


class AdminAppearanceTests(TestCase):
    def test_admin_login_has_shared_prepaint_theme_and_branding(self):
        response = self.client.get('/admin/login/')
        self.assertContains(response, 'Dawana System Administration')
        self.assertContains(response, '/static/appearance.js')
        self.assertContains(response, 'data-appearance-toggle')
        self.assertContains(response, 'role="switch"')
        self.assertNotContains(response, 'data-appearance-size')
        self.assertNotContains(response, '/static/admin/js/theme.js')
        self.assertIsNotNone(finders.find('theme.css'))
        self.assertIsNotNone(finders.find('appearance.js'))

    def test_operations_link_requires_permission_and_admin_still_requires_staff(self):
        user = get_user_model().objects.create_user(username='appearance-test', password='test-only', is_staff=True)
        self.client.force_login(user)
        self.assertNotContains(self.client.get('/admin/'), 'href="/dic/operations"')
        user.user_permissions.add(Permission.objects.get(content_type__app_label='dic', codename='can_view_dic_operations'))
        self.assertContains(self.client.get('/admin/'), 'href="/dic/operations"')
        user.is_staff = False
        user.save()
        self.assertEqual(self.client.get('/admin/').status_code, 302)
