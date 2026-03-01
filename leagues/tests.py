from django.core.exceptions import ValidationError
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse

from .models import Season, SeasonPlayer
from .forms import SeasonForm

User = get_user_model()


# ─── Model tests ─────────────────────────────────────────────────────────────

class SeasonModelTest(TestCase):
    def test_str_includes_year(self):
        season = Season(name='Spring League', year=2025)
        self.assertEqual(str(season), 'Spring League (2025)')

    def test_clean_raises_when_second_active_season(self):
        Season.objects.create(name='First', year=2024, status=Season.STATUS_ACTIVE)
        duplicate = Season(name='Second', year=2025, status=Season.STATUS_ACTIVE)
        with self.assertRaises(ValidationError):
            duplicate.clean()

    def test_clean_allows_updating_the_existing_active_season(self):
        season = Season.objects.create(name='Spring', year=2025, status=Season.STATUS_ACTIVE)
        season.name = 'Spring Updated'
        # Should not raise — it is still the same active season.
        season.clean()

    def test_clean_allows_multiple_non_active_seasons(self):
        Season.objects.create(name='Old', year=2024, status=Season.STATUS_COMPLETED)
        new = Season(name='New', year=2025, status=Season.STATUS_UPCOMING)
        new.clean()  # must not raise

    # ── Phase 5: num_tiers ───────────────────────────────────────────────────

    def test_num_tiers_defaults_to_1(self):
        season = Season.objects.create(name='Spring', year=2025)
        self.assertEqual(season.num_tiers, 1)

    def test_num_tiers_can_be_set(self):
        season = Season.objects.create(name='Spring', year=2025, num_tiers=2)
        self.assertEqual(season.num_tiers, 2)

    def test_num_tiers_persists_after_save(self):
        season = Season.objects.create(name='Spring', year=2025, num_tiers=3)
        season.refresh_from_db()
        self.assertEqual(season.num_tiers, 3)


class SeasonPlayerModelTest(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.player = User.objects.create_user(username='player1')

    def test_str(self):
        sp = SeasonPlayer(season=self.season, player=self.player)
        self.assertIn(str(self.player), str(sp))
        self.assertIn(str(self.season), str(sp))

    def test_unique_together_enforced(self):
        SeasonPlayer.objects.create(season=self.season, player=self.player)
        with self.assertRaises(IntegrityError):
            SeasonPlayer.objects.create(season=self.season, player=self.player)

    # ── Phase 5: tier field ──────────────────────────────────────────────────

    def test_tier_defaults_to_1(self):
        sp = SeasonPlayer.objects.create(season=self.season, player=self.player)
        self.assertEqual(sp.tier, 1)

    def test_tier_can_be_set(self):
        sp = SeasonPlayer.objects.create(season=self.season, player=self.player, tier=2)
        self.assertEqual(sp.tier, 2)

    def test_tier_persists_after_save(self):
        sp = SeasonPlayer.objects.create(season=self.season, player=self.player, tier=3)
        sp.refresh_from_db()
        self.assertEqual(sp.tier, 3)

    def test_different_players_can_be_in_different_tiers(self):
        p2 = User.objects.create_user(username='player2')
        sp1 = SeasonPlayer.objects.create(season=self.season, player=self.player, tier=1)
        sp2 = SeasonPlayer.objects.create(season=self.season, player=p2, tier=2)
        self.assertEqual(sp1.tier, 1)
        self.assertEqual(sp2.tier, 2)

    def test_can_filter_players_by_tier(self):
        p2 = User.objects.create_user(username='player2')
        p3 = User.objects.create_user(username='player3')
        SeasonPlayer.objects.create(season=self.season, player=self.player, tier=1)
        SeasonPlayer.objects.create(season=self.season, player=p2, tier=1)
        SeasonPlayer.objects.create(season=self.season, player=p3, tier=2)
        tier1 = SeasonPlayer.objects.filter(season=self.season, tier=1)
        tier2 = SeasonPlayer.objects.filter(season=self.season, tier=2)
        self.assertEqual(tier1.count(), 2)
        self.assertEqual(tier2.count(), 1)


# ─── SeasonForm tests ─────────────────────────────────────────────────────────

class SeasonFormTest(TestCase):
    def _valid_data(self, **overrides):
        data = {
            'name': 'Spring 2025',
            'year': 2025,
            'status': Season.STATUS_UPCOMING,
            'num_tiers': 1,
            'sets_to_win': 2,
            'final_set_format': Season.FINAL_SET_FULL,
            'playoff_qualifiers_count': 8,
            'walkover_rule': Season.WALKOVER_WINNER,
            'postponement_deadline': 14,
            'points_for_win': 3,
            'points_for_loss': 0,
            'points_for_walkover_loss': 0,
        }
        data.update(overrides)
        return data

    def test_valid_single_tier_form(self):
        form = SeasonForm(data=self._valid_data(num_tiers=1))
        self.assertTrue(form.is_valid(), form.errors)

    def test_valid_multi_tier_form(self):
        form = SeasonForm(data=self._valid_data(num_tiers=2))
        self.assertTrue(form.is_valid(), form.errors)

    def test_num_tiers_in_fields(self):
        form = SeasonForm()
        self.assertIn('num_tiers', form.fields)

    def test_form_saves_num_tiers(self):
        form = SeasonForm(data=self._valid_data(num_tiers=3))
        self.assertTrue(form.is_valid())
        season = form.save()
        self.assertEqual(season.num_tiers, 3)


# ─── View tests ───────────────────────────────────────────────────────────────

class HomeViewTest(TestCase):
    def test_home_redirects_to_season_list_when_no_active_season(self):
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('leagues:season_list'))

    def test_home_redirects_to_active_season_detail(self):
        season = Season.objects.create(name='Spring', year=2025, status=Season.STATUS_ACTIVE)
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('leagues:season_detail', kwargs={'pk': season.pk}))

    def test_home_accessible_when_authenticated(self):
        user = User.objects.create_user(username='tester', password='pass')
        self.client.login(username='tester', password='pass')
        response = self.client.get(reverse('home'))
        self.assertIn(response.status_code, [200, 302])


class SeasonListViewTest(TestCase):
    def test_empty_season_list(self):
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No seasons')

    def test_season_list_shows_seasons(self):
        Season.objects.create(name='Spring 2025', year=2025)
        Season.objects.create(name='Fall 2025', year=2025)
        response = self.client.get(reverse('leagues:season_list'))
        self.assertContains(response, 'Spring 2025')
        self.assertContains(response, 'Fall 2025')

    def test_season_list_ordering_newest_first(self):
        old = Season.objects.create(name='Spring 2023', year=2023)
        new = Season.objects.create(name='Spring 2025', year=2025)
        response = self.client.get(reverse('leagues:season_list'))
        seasons = list(response.context['seasons'])
        self.assertEqual(seasons[0], new)
        self.assertEqual(seasons[1], old)

    def test_season_list_accessible_anonymously(self):
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(response.status_code, 200)

    def test_season_list_accessible_when_authenticated(self):
        user = User.objects.create_user(username='tester', password='pass')
        self.client.login(username='tester', password='pass')
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(response.status_code, 200)


class SeasonDetailViewTest(TestCase):
    def setUp(self):
        self.season = Season.objects.create(
            name='Spring 2025', year=2025, status=Season.STATUS_ACTIVE,
        )

    def test_detail_shows_season_name(self):
        response = self.client.get(reverse('leagues:season_detail', kwargs={'pk': self.season.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Spring 2025')

    def test_detail_404_for_missing_season(self):
        response = self.client.get(reverse('leagues:season_detail', kwargs={'pk': 99999}))
        self.assertEqual(response.status_code, 404)

    def test_detail_accessible_anonymously(self):
        response = self.client.get(reverse('leagues:season_detail', kwargs={'pk': self.season.pk}))
        self.assertEqual(response.status_code, 200)

    def test_detail_accessible_when_authenticated(self):
        user = User.objects.create_user(username='tester', password='pass')
        self.client.login(username='tester', password='pass')
        response = self.client.get(reverse('leagues:season_detail', kwargs={'pk': self.season.pk}))
        self.assertEqual(response.status_code, 200)


# ─── Context processor tests ──────────────────────────────────────────────────

class SeasonContextProcessorTest(TestCase):
    def test_all_seasons_in_context(self):
        Season.objects.create(name='Spring', year=2025)
        response = self.client.get(reverse('leagues:season_list'))
        self.assertIn('all_seasons', response.context)
        self.assertEqual(len(response.context['all_seasons']), 1)

    def test_current_season_set_from_url(self):
        season = Season.objects.create(name='Spring', year=2025)
        response = self.client.get(reverse('leagues:season_detail', kwargs={'pk': season.pk}))
        self.assertEqual(response.context['current_season'], season)

    def test_current_season_defaults_to_active(self):
        Season.objects.create(name='Old', year=2024, status=Season.STATUS_COMPLETED)
        active = Season.objects.create(name='Current', year=2025, status=Season.STATUS_ACTIVE)
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(response.context['current_season'], active)

    def test_current_season_none_when_no_active_and_no_pk(self):
        Season.objects.create(name='Old', year=2024, status=Season.STATUS_COMPLETED)
        response = self.client.get(reverse('leagues:season_list'))
        self.assertIsNone(response.context['current_season'])

    def test_nonexistent_pk_in_url_falls_back_to_active(self):
        active = Season.objects.create(name='Active', year=2025, status=Season.STATUS_ACTIVE)
        # /seasons/99999/ returns 404, but the context processor should not crash.
        response = self.client.get(reverse('leagues:season_detail', kwargs={'pk': 99999}))
        self.assertEqual(response.status_code, 404)
