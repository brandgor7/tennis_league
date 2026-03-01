from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse

from .models import Season, SeasonPlayer

User = get_user_model()


class SeasonModelTest(TestCase):
    def test_str_includes_year(self):
        season = Season(name='Spring League', year=2025)
        self.assertEqual(str(season), 'Spring League (2025)')


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


class HomeViewTest(TestCase):
    def test_home_redirects_to_season_list_when_no_active_season(self):
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('leagues:season_list'))

    def test_home_redirects_to_active_season_detail(self):
        season = Season.objects.create(name='Spring', year=2025, status=Season.STATUS_ACTIVE)
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('leagues:season_detail', kwargs={'pk': season.pk}))


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


class SeasonContextProcessorTest(TestCase):
    def test_all_seasons_in_context(self):
        Season.objects.create(name='Spring', year=2025)
        response = self.client.get(reverse('leagues:season_list'))
        self.assertIn('all_seasons', response.context)
        self.assertEqual(response.context['all_seasons'].count(), 1)

    def test_current_season_set_from_url(self):
        season = Season.objects.create(name='Spring', year=2025)
        response = self.client.get(reverse('leagues:season_detail', kwargs={'pk': season.pk}))
        self.assertEqual(response.context['current_season'], season)

    def test_current_season_defaults_to_active(self):
        Season.objects.create(name='Old', year=2024, status=Season.STATUS_COMPLETED)
        active = Season.objects.create(name='Current', year=2025, status=Season.STATUS_ACTIVE)
        response = self.client.get(reverse('leagues:season_list'))
        self.assertEqual(response.context['current_season'], active)
