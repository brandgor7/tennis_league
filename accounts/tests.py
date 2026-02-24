from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()


class UserModelTest(TestCase):
    def test_str(self):
        user = User(username='jdoe')
        self.assertEqual(str(user), 'jdoe')
