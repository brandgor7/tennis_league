from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from leagues.models import Season
from matches.models import Match

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

    def test_authenticated_navbar_shows_profile_link(self):
        self._make_user(username='tester')
        self.client.login(username='tester', password='testpass123')
        response = self.client.get(self.login_url)
        self.assertContains(response, 'My Profile')


class ProfileViewTest(TestCase):
    def setUp(self):
        self.url = reverse('accounts:profile')
        self.user = User.objects.create_user(username='me', password='testpass123')
        self.opponent = User.objects.create_user(
            username='opponent', password='testpass123',
            first_name='Jane', last_name='Doe',
        )
        self.season = Season.objects.create(name='Spring 2025', year=2025)

    def _make_match(self, player1=None, player2=None, winner=None,
                    status=Match.STATUS_COMPLETED):
        return Match.objects.create(
            season=self.season,
            player1=player1 or self.user,
            player2=player2 or self.opponent,
            status=status,
            winner=winner,
        )

    # ── Access control ────────────────────────────────────────────

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(
            response, f'/accounts/login/?next={self.url}',
            fetch_redirect_response=False,
        )

    def test_authenticated_gets_200(self):
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_uses_correct_template(self):
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'accounts/profile.html')

    # ── Match filtering ───────────────────────────────────────────

    def test_shows_completed_match_as_player1(self):
        self._make_match(winner=self.user)
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['history']), 1)

    def test_shows_completed_match_as_player2(self):
        self._make_match(player1=self.opponent, player2=self.user, winner=self.user)
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['history']), 1)

    def test_shows_walkover_match(self):
        self._make_match(winner=self.user, status=Match.STATUS_WALKOVER)
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['history']), 1)

    def test_excludes_scheduled_matches(self):
        self._make_match(status=Match.STATUS_SCHEDULED)
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['history']), 0)

    def test_excludes_other_players_matches(self):
        other = User.objects.create_user(username='other', password='testpass123')
        self._make_match(player1=self.opponent, player2=other, winner=self.opponent)
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['history']), 0)

    # ── Win/loss counts ───────────────────────────────────────────

    def test_win_counts(self):
        self._make_match(winner=self.user)
        self._make_match(winner=self.opponent)
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.context['wins'], 1)
        self.assertEqual(response.context['losses'], 1)

    def test_walkover_win_counts_as_win(self):
        self._make_match(winner=self.user, status=Match.STATUS_WALKOVER)
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.context['wins'], 1)
        self.assertEqual(response.context['losses'], 0)

    def test_no_winner_not_counted(self):
        # Walkover with winner=None shouldn't count as win or loss
        self._make_match(winner=None, status=Match.STATUS_WALKOVER)
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.context['wins'], 0)
        self.assertEqual(response.context['losses'], 0)

    # ── Opponent resolution ───────────────────────────────────────

    def test_opponent_is_player2_when_user_is_player1(self):
        self._make_match(winner=self.user)
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.context['history'][0]['opponent'], self.opponent)

    def test_opponent_is_player1_when_user_is_player2(self):
        self._make_match(player1=self.opponent, player2=self.user, winner=self.user)
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertEqual(response.context['history'][0]['opponent'], self.opponent)

    # ── Template output ───────────────────────────────────────────

    def test_opponent_name_appears_in_page(self):
        self._make_match(winner=self.user)
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertContains(response, 'Jane Doe')

    def test_empty_state_shown_when_no_matches(self):
        self.client.login(username='me', password='testpass123')
        response = self.client.get(self.url)
        self.assertContains(response, 'No completed matches yet')
