from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class UserModelTest(TestCase):
    def test_str(self):
        user = User(username='jdoe')
        self.assertEqual(str(user), 'jdoe')


class LoginViewTest(TestCase):
    def setUp(self):
        self.url = reverse('accounts:login')
        self.user = User.objects.create_user(
            username='player1',
            password='testpass123',
            first_name='Anna',
            last_name='Kournikova',
        )

    # ── GET ──────────────────────────────────────────────────────

    def test_login_page_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_login_page_uses_correct_template(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'accounts/login.html')
        self.assertTemplateUsed(response, 'base.html')

    def test_login_page_contains_form(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<form')
        self.assertContains(response, 'csrfmiddlewaretoken')

    # ── POST: valid credentials ───────────────────────────────────

    def test_valid_login_redirects(self):
        response = self.client.post(self.url, {
            'username': 'player1',
            'password': 'testpass123',
        })
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_valid_login_creates_session(self):
        self.client.post(self.url, {
            'username': 'player1',
            'password': 'testpass123',
        })
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_respects_next_param(self):
        response = self.client.post(
            f'{self.url}?next=/admin/',
            {'username': 'player1', 'password': 'testpass123'},
        )
        self.assertRedirects(response, '/admin/', fetch_redirect_response=False)

    # ── POST: invalid credentials ─────────────────────────────────

    def test_invalid_login_stays_on_page(self):
        response = self.client.post(self.url, {
            'username': 'player1',
            'password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)

    def test_invalid_login_shows_error(self):
        response = self.client.post(self.url, {
            'username': 'player1',
            'password': 'wrongpassword',
        })
        self.assertContains(response, 'Invalid username or password')

    def test_invalid_login_no_session(self):
        self.client.post(self.url, {
            'username': 'player1',
            'password': 'wrongpassword',
        })
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_nonexistent_user_shows_error(self):
        response = self.client.post(self.url, {
            'username': 'nobody',
            'password': 'testpass123',
        })
        self.assertContains(response, 'Invalid username or password')


class LogoutViewTest(TestCase):
    def setUp(self):
        self.url = reverse('accounts:logout')
        self.user = User.objects.create_user(
            username='player1',
            password='testpass123',
        )
        self.client.login(username='player1', password='testpass123')

    def test_logout_post_redirects_to_login(self):
        response = self.client.post(self.url)
        self.assertRedirects(
            response, reverse('accounts:login'), fetch_redirect_response=False
        )

    def test_logout_clears_session(self):
        self.client.post(self.url)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_get_not_allowed(self):
        # Django 5.x LogoutView requires POST; GET should not log the user out
        self.client.get(self.url)
        self.assertIn('_auth_user_id', self.client.session)


class NavbarTemplateTest(TestCase):
    """Sanity-check that base.html renders the right nav state."""

    def setUp(self):
        self.login_url = reverse('accounts:login')

    def _make_user(self, **kwargs):
        defaults = {'username': 'tester', 'password': 'testpass123'}
        defaults.update(kwargs)
        password = defaults.pop('password')
        user = User.objects.create_user(**defaults)
        user.set_password(password)
        user.save()
        return user

    def test_unauthenticated_shows_sign_in_link(self):
        response = self.client.get(self.login_url)
        self.assertContains(response, 'Sign In')
        self.assertNotContains(response, 'Sign Out')

    def test_authenticated_shows_sign_out(self):
        self._make_user(username='tester')
        self.client.login(username='tester', password='testpass123')
        response = self.client.get(self.login_url)
        self.assertContains(response, 'Sign Out')
        self.assertNotContains(response, 'href="/accounts/login/"')

    def test_avatar_uses_initials_when_name_set(self):
        self._make_user(username='tester', first_name='Anna', last_name='Smith')
        self.client.login(username='tester', password='testpass123')
        response = self.client.get(self.login_url)
        self.assertContains(response, 'AS')

    def test_avatar_falls_back_to_username_initial(self):
        # User with no first/last name — avatar should show username initial
        self._make_user(username='tester')
        self.client.login(username='tester', password='testpass123')
        response = self.client.get(self.login_url)
        self.assertContains(response, 'T')  # first letter of 'tester', uppercased

    def test_staff_user_sees_admin_link(self):
        self._make_user(username='admin_user', is_staff=True)
        self.client.login(username='admin_user', password='testpass123')
        response = self.client.get(self.login_url)
        self.assertContains(response, 'href="/admin/"')

    def test_non_staff_user_does_not_see_admin_link(self):
        self._make_user(username='tester')
        self.client.login(username='tester', password='testpass123')
        response = self.client.get(self.login_url)
        self.assertNotContains(response, 'href="/admin/"')
