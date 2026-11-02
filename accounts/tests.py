from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_and_login_case_insensitive(self):
        res = self.client.post(
            '/api/accounts/register/',
            {
                'first_name': 'Test',
                'last_name': 'User',
                'email': 'User@Example.com',
                'password': 'StrongPass123!',
                'password2': 'StrongPass123!',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 201, res.data)

        res = self.client.post(
            '/api/accounts/login/',
            {'email': 'USER@EXAMPLE.COM', 'password': 'StrongPass123!'},
            format='json',
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIn('access', res.data)

    def test_duplicate_email_is_400(self):
        User.objects.create_user(
            email='dup@example.com', password='StrongPass123!'
        )
        res = self.client.post(
            '/api/accounts/register/',
            {
                'first_name': 'A',
                'last_name': 'B',
                'email': 'DUP@example.com',
                'password': 'StrongPass123!',
                'password2': 'StrongPass123!',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    def test_profile_update_normalizes_email(self):
        user = User.objects.create_user(
            email='profile@example.com', password='StrongPass123!'
        )
        self.client.force_authenticate(user)
        res = self.client.patch(
            '/api/accounts/profile/',
            {'email': 'PROFILE@EXAMPLE.COM'},
            format='json',
        )
        self.assertEqual(res.status_code, 200, res.data)
        user.refresh_from_db()
        self.assertEqual(user.email, 'profile@example.com')

    def test_change_password_requires_correct_old_password(self):
        user = User.objects.create_user(
            email='pw@example.com', password='StrongPass123!'
        )
        self.client.force_authenticate(user)
        res = self.client.post(
            '/api/accounts/change-password/',
            {
                'old_password': 'WrongPass123!',
                'new_password': 'NewStrongPass456!',
                'new_password2': 'NewStrongPass456!',
            },
            format='json',
        )
        self.assertEqual(res.status_code, 400)