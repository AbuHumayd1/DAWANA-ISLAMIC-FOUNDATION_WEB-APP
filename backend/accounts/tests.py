from django.contrib.auth import authenticate, get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse


class AdminPasswordInterfaceTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="password-ui-admin", password="admin-test-only"
        )
        self.client.force_login(self.admin)

    def test_creation_and_password_change_pages_load_toggle_asset(self):
        for url in (reverse("admin:accounts_user_add"),
                    reverse("admin:auth_user_password_change", args=[self.admin.pk]),
                    reverse("admin:password_change")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, '/static/dic/password-toggle.js')
                self.assertContains(response, 'type="password"', count=None)
                self.assertNotContains(response, self.admin.password)
        self.assertIsNotNone(finders.find("dic/password-toggle.js"))

    def test_saved_password_widget_is_not_an_editable_password(self):
        response = self.client.get(reverse("admin:accounts_user_change", args=[self.admin.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'type="password"')
        self.assertNotContains(response, self.admin.password)

    def test_user_creation_still_validates_confirmation_and_hashes_password(self):
        url = reverse("admin:accounts_user_add")
        password = "Synthetic-new-account-83!"
        weak = self.client.post(url, {
            "username": "password-ui-user", "usable_password": "true",
            "password1": "password", "password2": "password", "_save": "Save",
        })
        self.assertEqual(weak.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="password-ui-user").exists())
        response = self.client.post(url, {
            "username": "password-ui-user", "usable_password": "true",
            "password1": password, "password2": "different", "_save": "Save",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="password-ui-user").exists())
        response = self.client.post(url, {
            "username": "password-ui-user", "usable_password": "true",
            "password1": password, "password2": password, "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="password-ui-user")
        self.assertNotEqual(user.password, password)
        self.assertTrue(user.check_password(password))
        self.assertEqual(authenticate(username=user.username, password=password).pk, user.pk)

    def test_admin_password_reset_preserves_validation_and_hashing(self):
        target = get_user_model().objects.create_user(username="password-reset-target", password="old-test-only")
        old_hash = target.password
        url = reverse("admin:auth_user_password_change", args=[target.pk])
        response = self.client.post(url, {
            "usable_password": "true", "password1": "Cedar-copper-lantern-84!", "password2": "different", "set-password": "Set password",
        })
        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.password, old_hash)
        response = self.client.post(url, {
            "usable_password": "true", "password1": "Cedar-copper-lantern-84!", "password2": "Cedar-copper-lantern-84!", "set-password": "Set password",
        })
        self.assertEqual(response.status_code, 302, response.context["form"].errors if response.status_code == 200 else "")
        target.refresh_from_db()
        self.assertNotEqual(target.password, old_hash)
        self.assertTrue(target.check_password("Cedar-copper-lantern-84!"))
        self.assertIsNone(authenticate(username=target.username, password="old-test-only"))
        self.assertEqual(authenticate(username=target.username, password="Cedar-copper-lantern-84!").pk, target.pk)
