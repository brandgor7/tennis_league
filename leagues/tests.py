import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse

from .models import Season, SeasonPlayer
from .forms import SeasonForm
from matches.models import Match

User = get_user_model()


# ─── Shared helpers ───────────────────────────────────────────────────────────

def make_season(**kwargs):
    defaults = dict(
        name='Spring 2025', year=2025,
        status=Season.STATUS_ACTIVE,
        num_tiers=1,
        points_for_win=3,
        points_for_loss=0,
        points_for_walkover_loss=0,
        walkover_rule=Season.WALKOVER_WINNER,
    )
    defaults.update(kwargs)
    return Season.objects.create(**defaults)


def make_player(username, first='', last=''):
    return User.objects.create_user(username=username, first_name=first, last_name=last)


def enroll(season, player, tier=1, is_active=True):
    return SeasonPlayer.objects.create(season=season, player=player, tier=tier, is_active=is_active)


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
            'schedule_type': Season.SCHEDULE_WEEKLY,
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

    def test_home_redirects_to_active_season_standings(self):
        season = Season.objects.create(name='Spring', year=2025, status=Season.STATUS_ACTIVE)
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('leagues:standings', kwargs={'slug': season.slug}))

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
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': self.season.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Spring 2025')

    def test_detail_404_for_missing_season(self):
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': 'nonexistent-season'}))
        self.assertEqual(response.status_code, 404)

    def test_detail_accessible_anonymously(self):
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': self.season.slug}))
        self.assertEqual(response.status_code, 200)

    def test_detail_accessible_when_authenticated(self):
        user = User.objects.create_user(username='tester', password='pass')
        self.client.login(username='tester', password='pass')
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': self.season.slug}))
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
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': season.slug}))
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

    def test_nonexistent_slug_in_url_falls_back_to_active(self):
        active = Season.objects.create(name='Active', year=2025, status=Season.STATUS_ACTIVE)
        # /seasons/nonexistent-season/ returns 404, but the context processor should not crash.
        response = self.client.get(reverse('leagues:season_detail', kwargs={'slug': 'nonexistent-season'}))
        self.assertEqual(response.status_code, 404)


# ─── SeasonPlayerDetailView tests ────────────────────────────────────────────

class SeasonPlayerDetailViewTest(TestCase):
    def setUp(self):
        self.season = make_season(num_tiers=1)
        self.player = make_player('alice', first='Alice', last='Smith')
        enroll(self.season, self.player, tier=1)
        self.url = reverse('leagues:player_detail', kwargs={
            'slug': self.season.slug,
            'username': self.player.username,
        })

    def _make_match(self, p1, p2, status, winner=None, tier=1):
        return Match.objects.create(
            season=self.season, player1=p1, player2=p2,
            tier=tier, status=status, winner=winner,
            scheduled_date=datetime.date(2025, 6, 1),
        )

    def test_200_for_valid_player_in_season(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_404_for_missing_season(self):
        url = reverse('leagues:player_detail', kwargs={'slug': 'nonexistent-season', 'username': self.player.username})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_404_for_missing_player(self):
        url = reverse('leagues:player_detail', kwargs={'slug': self.season.slug, 'username': 'nonexistent-user'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_404_when_player_not_enrolled_in_season(self):
        other = make_player('outsider')
        url = reverse('leagues:player_detail', kwargs={'slug': self.season.slug, 'username': other.username})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_404_when_player_is_inactive(self):
        inactive = make_player('inactive')
        enroll(self.season, inactive, tier=1, is_active=False)
        url = reverse('leagues:player_detail', kwargs={'slug': self.season.slug, 'username': inactive.username})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_uses_correct_template(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'leagues/player_detail.html')

    def test_season_in_context(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['season'], self.season)

    def test_player_in_context(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['player'], self.player)

    def test_season_player_in_context(self):
        response = self.client.get(self.url)
        sp = response.context['season_player']
        self.assertEqual(sp.player, self.player)
        self.assertEqual(sp.season, self.season)

    def test_standing_present_for_enrolled_player_with_no_matches(self):
        response = self.client.get(self.url)
        self.assertIsNotNone(response.context['standing'])
        self.assertIsNotNone(response.context['rank'])

    def test_standing_zeros_when_no_matches_played(self):
        response = self.client.get(self.url)
        standing = response.context['standing']
        self.assertEqual(standing['wins'], 0)
        self.assertEqual(standing['losses'], 0)
        self.assertEqual(standing['points'], 0)

    def test_standing_reflects_completed_match_win(self):
        opponent = make_player('opponent')
        enroll(self.season, opponent, tier=1)
        Match.objects.create(
            season=self.season, player1=self.player, player2=opponent,
            tier=1, status=Match.STATUS_COMPLETED, winner=self.player,
        )
        response = self.client.get(self.url)
        standing = response.context['standing']
        self.assertEqual(standing['wins'], 1)
        self.assertEqual(standing['points'], self.season.points_for_win)

    def test_rank_1_when_player_is_sole_enrolled_player(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['rank'], 1)

    def test_rank_reflects_position_among_multiple_players(self):
        leader = make_player('leader')
        enroll(self.season, leader, tier=1)
        # leader beats self.player → leader is rank 1, self.player rank 2
        Match.objects.create(
            season=self.season, player1=leader, player2=self.player,
            tier=1, status=Match.STATUS_COMPLETED, winner=leader,
        )
        response = self.client.get(self.url)
        self.assertEqual(response.context['rank'], 2)

    def test_upcoming_contains_scheduled_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_SCHEDULED)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['upcoming']))

    def test_upcoming_contains_postponed_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_POSTPONED)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['upcoming']))

    def test_upcoming_excludes_matches_not_involving_player(self):
        other1 = make_player('o1')
        other2 = make_player('o2')
        enroll(self.season, other1, tier=1)
        enroll(self.season, other2, tier=1)
        unrelated = self._make_match(other1, other2, Match.STATUS_SCHEDULED)
        response = self.client.get(self.url)
        self.assertNotIn(unrelated, list(response.context['upcoming']))

    def test_upcoming_contains_pending_confirmation_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_PENDING)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['upcoming']))

    def test_upcoming_excludes_completed_matches(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_COMPLETED, winner=self.player)
        response = self.client.get(self.url)
        self.assertNotIn(m, list(response.context['upcoming']))

    def test_upcoming_excludes_matches_from_other_seasons(self):
        other_season = make_season(name='Other', status=Season.STATUS_UPCOMING)
        opponent = make_player('opp')
        enroll(other_season, self.player, tier=1)
        enroll(other_season, opponent, tier=1)
        other_match = Match.objects.create(
            season=other_season, player1=self.player, player2=opponent,
            tier=1, status=Match.STATUS_SCHEDULED,
            scheduled_date=datetime.date(2025, 6, 1),
        )
        response = self.client.get(self.url)
        self.assertNotIn(other_match, list(response.context['upcoming']))

    def test_results_contains_completed_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_COMPLETED, winner=self.player)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['results']))

    def test_results_contains_walkover_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_WALKOVER, winner=self.player)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['results']))

    def test_results_excludes_scheduled_match(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(self.player, opponent, Match.STATUS_SCHEDULED)
        response = self.client.get(self.url)
        self.assertNotIn(m, list(response.context['results']))

    def test_results_excludes_matches_not_involving_player(self):
        other1 = make_player('o1')
        other2 = make_player('o2')
        enroll(self.season, other1, tier=1)
        enroll(self.season, other2, tier=1)
        unrelated = self._make_match(other1, other2, Match.STATUS_COMPLETED, winner=other1)
        response = self.client.get(self.url)
        self.assertNotIn(unrelated, list(response.context['results']))

    def test_player_as_player2_appears_in_upcoming(self):
        """Player should appear in upcoming whether they are player1 or player2."""
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(opponent, self.player, Match.STATUS_SCHEDULED)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['upcoming']))

    def test_player_as_player2_appears_in_results(self):
        opponent = make_player('opp')
        enroll(self.season, opponent, tier=1)
        m = self._make_match(opponent, self.player, Match.STATUS_COMPLETED, winner=opponent)
        response = self.client.get(self.url)
        self.assertIn(m, list(response.context['results']))

    def test_accessible_anonymously(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_player_name_in_response(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Alice Smith')


# ─── SeasonPlayerDetailView template tests ────────────────────────────────────

class SeasonPlayerDetailTemplateTest(TestCase):
    def setUp(self):
        self.season = make_season(num_tiers=1)
        self.player = make_player('alice', first='Alice', last='Smith')
        enroll(self.season, self.player, tier=1)
        self.url = reverse('leagues:player_detail', kwargs={
            'slug': self.season.slug, 'username': self.player.username,
        })

    def _opponent(self, username='opp'):
        p = make_player(username)
        enroll(self.season, p, tier=1)
        return p

    def test_player_name_in_heading(self):
        response = self.client.get(self.url)
        self.assertContains(response, '<h1>Alice Smith</h1>')

    def test_season_name_in_page_meta(self):
        response = self.client.get(self.url)
        self.assertContains(response, self.season.name)

    def test_tier_label_shown_for_multi_tier_season(self):
        season = make_season(num_tiers=2, name='Multi', status=Season.STATUS_UPCOMING)
        p = make_player('bob', first='Bob', last='Jones')
        enroll(season, p, tier=2)
        url = reverse('leagues:player_detail', kwargs={'slug': season.slug, 'username': p.username})
        response = self.client.get(url)
        self.assertContains(response, 'Tier 2')

    def test_tier_label_not_shown_for_single_tier_season(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Tier 1')

    def test_standing_stats_rendered(self):
        opp = self._opponent()
        Match.objects.create(
            season=self.season, player1=self.player, player2=opp,
            tier=1, status=Match.STATUS_COMPLETED, winner=self.player,
        )
        response = self.client.get(self.url)
        self.assertContains(response, 'Rank')
        self.assertContains(response, 'Wins')
        self.assertContains(response, 'Losses')
        self.assertContains(response, 'Pts')
        self.assertContains(response, 'PD')

    def test_rank_top3_highlight_applied_for_rank_1(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'rank-top-3')

    def test_upcoming_section_heading_present(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Upcoming Matches')

    def test_results_section_heading_present(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Results')

    def test_upcoming_match_opponent_name_rendered(self):
        opp = self._opponent('carol')
        opp.first_name = 'Carol'
        opp.last_name = 'White'
        opp.save()
        Match.objects.create(
            season=self.season, player1=self.player, player2=opp,
            tier=1, status=Match.STATUS_SCHEDULED,
            scheduled_date=datetime.date(2025, 6, 1),
        )
        response = self.client.get(self.url)
        self.assertContains(response, 'Carol White')

    def test_completed_match_rendered_in_results(self):
        opp = self._opponent('dave')
        opp.first_name = 'Dave'
        opp.last_name = 'Black'
        opp.save()
        Match.objects.create(
            season=self.season, player1=self.player, player2=opp,
            tier=1, status=Match.STATUS_COMPLETED, winner=self.player,
        )
        response = self.client.get(self.url)
        self.assertContains(response, 'Dave Black')
