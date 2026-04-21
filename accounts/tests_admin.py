import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.admin import PlayerAddForm
from leagues.models import Season, SeasonPlayer, Tier

User = get_user_model()


def make_season(name='Spring 2025', year=2025, tiers=1, **kwargs):
    """Create a Season with the given number of auto-named Tier objects."""
    defaults = dict(
        name=name, year=year,
        status=Season.STATUS_ACTIVE,
        points_for_win=3, points_for_loss=0, points_for_walkover_loss=0,
        walkover_rule=Season.WALKOVER_WINNER,
    )
    defaults.update(kwargs)
    season = Season.objects.create(**defaults)
    for n in range(1, tiers + 1):
        Tier.objects.create(season=season, number=n, name=f'Tier {n}')
    return season


def form_data(**overrides):
    defaults = {
        'first_name': 'Jane',
        'last_name': 'Doe',
        'username': 'janedoe',
        'email': '',
        'set_password': False,
        'password1': '',
        'password2': '',
        'season': '',
        'tier': '',
    }
    defaults.update(overrides)
    return defaults


# ─── PlayerAddForm ────────────────────────────────────────────────────────────

class PlayerAddFormValidationTest(TestCase):

    def test_valid_minimal(self):
        f = PlayerAddForm(data=form_data())
        self.assertTrue(f.is_valid(), f.errors)

    def test_first_and_last_name_required(self):
        f = PlayerAddForm(data=form_data(first_name='', last_name=''))
        self.assertFalse(f.is_valid())
        self.assertIn('first_name', f.errors)
        self.assertIn('last_name', f.errors)

    def test_username_required(self):
        f = PlayerAddForm(data=form_data(username=''))
        self.assertFalse(f.is_valid())
        self.assertIn('username', f.errors)

    def test_email_optional(self):
        f = PlayerAddForm(data=form_data(email=''))
        self.assertTrue(f.is_valid(), f.errors)

    def test_email_validated_when_provided(self):
        f = PlayerAddForm(data=form_data(email='not-an-email'))
        self.assertFalse(f.is_valid())
        self.assertIn('email', f.errors)

    def test_set_password_off_no_password_fields_required(self):
        f = PlayerAddForm(data=form_data(set_password=False, password1='', password2=''))
        self.assertTrue(f.is_valid(), f.errors)

    def test_set_password_on_requires_password(self):
        f = PlayerAddForm(data=form_data(set_password=True, password1='', password2=''))
        self.assertFalse(f.is_valid())
        self.assertIn('password1', f.errors)

    def test_set_password_on_mismatch_raises_error(self):
        f = PlayerAddForm(data=form_data(set_password=True, password1='abc123', password2='different'))
        self.assertFalse(f.is_valid())
        self.assertIn('password2', f.errors)

    def test_set_password_on_matching_passwords_valid(self):
        f = PlayerAddForm(data=form_data(set_password=True, password1='correct', password2='correct'))
        self.assertTrue(f.is_valid(), f.errors)

    def test_season_without_tier_valid(self):
        season = make_season()
        f = PlayerAddForm(data=form_data(season=season.pk, tier=''))
        self.assertTrue(f.is_valid(), f.errors)

    def test_tier_out_of_range_for_season(self):
        season = make_season(tiers=2)
        f = PlayerAddForm(data=form_data(season=season.pk, tier=3))
        self.assertFalse(f.is_valid())
        self.assertIn('tier', f.errors)

    def test_tier_at_boundary_valid(self):
        season = make_season(tiers=3)
        f = PlayerAddForm(data=form_data(season=season.pk, tier=3))
        self.assertTrue(f.is_valid(), f.errors)

    def test_tier_without_season_ignored(self):
        f = PlayerAddForm(data=form_data(season='', tier=99))
        self.assertTrue(f.is_valid(), f.errors)


# ─── _tiers_json endpoint ─────────────────────────────────────────────────────

class TiersJsonViewTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser('admin', password='password')
        self.client.force_login(self.superuser)
        self.url = reverse('admin:accounts_user_tiers_json')

    def test_no_season_id_returns_empty_list(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content), [])

    def test_non_integer_season_id_returns_empty_list(self):
        resp = self.client.get(self.url, {'season_id': 'abc'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content), [])

    def test_nonexistent_season_id_returns_empty_list(self):
        resp = self.client.get(self.url, {'season_id': 9999})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content), [])

    def test_returns_tiers_for_season(self):
        season = Season.objects.create(name='Spring 2025', year=2025, status=Season.STATUS_ACTIVE,
                                       points_for_win=3, points_for_loss=0, points_for_walkover_loss=0,
                                       walkover_rule=Season.WALKOVER_WINNER)
        Tier.objects.create(season=season, number=1, name='Premier')
        Tier.objects.create(season=season, number=2, name='Division 1')
        resp = self.client.get(self.url, {'season_id': season.pk})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0], {'number': 1, 'name': 'Premier'})
        self.assertEqual(data[1], {'number': 2, 'name': 'Division 1'})

    def test_tiers_ordered_by_number(self):
        season = Season.objects.create(name='Spring 2025', year=2025, status=Season.STATUS_ACTIVE,
                                       points_for_win=3, points_for_loss=0, points_for_walkover_loss=0,
                                       walkover_rule=Season.WALKOVER_WINNER)
        Tier.objects.create(season=season, number=3, name='Third')
        Tier.objects.create(season=season, number=1, name='First')
        resp = self.client.get(self.url, {'season_id': season.pk})
        data = json.loads(resp.content)
        self.assertEqual([t['number'] for t in data], [1, 3])

    def test_requires_authentication(self):
        self.client.logout()
        resp = self.client.get(self.url)
        self.assertNotEqual(resp.status_code, 200)

    def test_tiers_from_other_season_excluded(self):
        season_a = make_season(name='A', year=2024, tiers=0)
        season_b = make_season(name='B', year=2025, tiers=0)
        Tier.objects.create(season=season_a, number=1, name='A Premier')
        Tier.objects.create(season=season_b, number=1, name='B Premier')
        resp = self.client.get(self.url, {'season_id': season_a.pk})
        data = json.loads(resp.content)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], 'A Premier')


# ─── Admin add-player POST (save_model) ───────────────────────────────────────

class AdminAddPlayerTest(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser('admin', password='password')
        self.client.force_login(self.superuser)
        self.url = reverse('admin:accounts_user_add')

    def _post(self, **overrides):
        data = {
            'first_name': 'Jane',
            'last_name': 'Doe',
            'username': 'janedoe',
            'email': '',
            'set_password': '',
            'password1': '',
            'password2': '',
            'season': '',
            'tier': '',
        }
        data.update(overrides)
        return self.client.post(self.url, data, follow=True)

    def test_creates_user(self):
        self._post()
        self.assertTrue(User.objects.filter(username='janedoe').exists())

    def test_stores_first_and_last_name(self):
        self._post()
        user = User.objects.get(username='janedoe')
        self.assertEqual(user.first_name, 'Jane')
        self.assertEqual(user.last_name, 'Doe')

    def test_no_password_by_default_creates_unusable_password(self):
        self._post()
        user = User.objects.get(username='janedoe')
        self.assertFalse(user.has_usable_password())

    def test_set_password_creates_usable_password(self):
        self._post(set_password='on', password1='correct123', password2='correct123')
        user = User.objects.get(username='janedoe')
        self.assertTrue(user.check_password('correct123'))

    def test_mismatched_passwords_does_not_create_user(self):
        self._post(set_password='on', password1='abc', password2='xyz')
        self.assertFalse(User.objects.filter(username='janedoe').exists())

    def test_no_season_creates_no_season_player(self):
        self._post()
        user = User.objects.get(username='janedoe')
        self.assertFalse(SeasonPlayer.objects.filter(player=user).exists())

    def test_with_season_creates_season_player(self):
        season = make_season()
        self._post(season=season.pk, tier=1)
        user = User.objects.get(username='janedoe')
        sp = SeasonPlayer.objects.get(player=user, season=season)
        self.assertEqual(sp.tier, 1)

    def test_with_season_and_no_tier_defaults_to_1(self):
        season = make_season()
        self._post(season=season.pk, tier='')
        user = User.objects.get(username='janedoe')
        sp = SeasonPlayer.objects.get(player=user, season=season)
        self.assertEqual(sp.tier, 1)

    def test_with_season_stores_correct_tier(self):
        season = make_season(tiers=3)
        self._post(season=season.pk, tier=2)
        user = User.objects.get(username='janedoe')
        sp = SeasonPlayer.objects.get(player=user, season=season)
        self.assertEqual(sp.tier, 2)

    def test_tier_out_of_range_does_not_create_user(self):
        season = make_season(tiers=2)
        self._post(season=season.pk, tier=3)
        self.assertFalse(User.objects.filter(username='janedoe').exists())

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username='janedoe')
        self._post()
        self.assertEqual(User.objects.filter(username='janedoe').count(), 1)
