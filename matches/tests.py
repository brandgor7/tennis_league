import datetime

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from leagues.models import Season, SeasonPlayer, Tier
from .models import Match, MatchSet
from .forms import MatchScheduleForm, ResultEntryForm, WalkoverForm, PostponeForm
from .scheduler import _round_robin_rounds, generate_schedule

User = get_user_model()


class MatchCleanTest(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.p1 = User.objects.create_user(username='player1')
        self.p2 = User.objects.create_user(username='player2')
        self.p3 = User.objects.create_user(username='player3')

    def _match(self, **kwargs):
        return Match(season=self.season, player1=self.p1, player2=self.p2, **kwargs)

    def test_valid_match_passes(self):
        self._match().clean()

    def test_valid_match_with_winner_passes(self):
        self._match(winner=self.p1).clean()
        self._match(winner=self.p2).clean()

    def test_self_match_raises(self):
        match = Match(season=self.season, player1=self.p1, player2=self.p1)
        with self.assertRaises(ValidationError) as ctx:
            match.clean()
        self.assertIn('player2', ctx.exception.message_dict)

    def test_winner_outside_match_raises(self):
        match = self._match(winner=self.p3)
        with self.assertRaises(ValidationError) as ctx:
            match.clean()
        self.assertIn('winner', ctx.exception.message_dict)


class MatchTierFieldTest(TestCase):
    """Phase 5: Match.tier field."""

    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.p1 = User.objects.create_user(username='player1')
        self.p2 = User.objects.create_user(username='player2')

    def test_tier_defaults_to_null(self):
        match = Match.objects.create(season=self.season, player1=self.p1, player2=self.p2)
        self.assertIsNone(match.tier)

    def test_tier_can_be_set(self):
        match = Match.objects.create(season=self.season, player1=self.p1, player2=self.p2, tier=1)
        self.assertEqual(match.tier, 1)

    def test_tier_persists_after_save(self):
        match = Match.objects.create(season=self.season, player1=self.p1, player2=self.p2, tier=2)
        match.refresh_from_db()
        self.assertEqual(match.tier, 2)

    def test_can_filter_matches_by_tier(self):
        p3 = User.objects.create_user(username='player3')
        p4 = User.objects.create_user(username='player4')
        Match.objects.create(season=self.season, player1=self.p1, player2=self.p2, tier=1)
        Match.objects.create(season=self.season, player1=self.p1, player2=self.p2, tier=1)
        Match.objects.create(season=self.season, player1=p3, player2=p4, tier=2)
        self.assertEqual(Match.objects.filter(tier=1).count(), 2)
        self.assertEqual(Match.objects.filter(tier=2).count(), 1)

    def test_match_clean_still_validates_players(self):
        """Tier field doesn't break existing clean() logic."""
        match = Match(season=self.season, player1=self.p1, player2=self.p1, tier=1)
        with self.assertRaises(ValidationError):
            match.clean()


class MatchSetCleanTest(TestCase):
    def setUp(self):
        season = Season.objects.create(name='Spring', year=2025)
        p1 = User.objects.create_user(username='player1')
        p2 = User.objects.create_user(username='player2')
        self.match = Match.objects.create(season=season, player1=p1, player2=p2)

    def _set(self, **kwargs):
        defaults = dict(match=self.match, set_number=1, player1_games=6, player2_games=4)
        defaults.update(kwargs)
        return MatchSet(**defaults)

    def test_no_tiebreak_passes(self):
        self._set().clean()

    def test_both_tiebreak_fields_set_passes(self):
        self._set(player1_games=7, player2_games=6,
                  tiebreak_player1_points=7, tiebreak_player2_points=5).clean()

    def test_only_player1_tiebreak_raises(self):
        ms = self._set(tiebreak_player1_points=7, tiebreak_player2_points=None)
        with self.assertRaises(ValidationError):
            ms.clean()

    def test_only_player2_tiebreak_raises(self):
        ms = self._set(tiebreak_player1_points=None, tiebreak_player2_points=5)
        with self.assertRaises(ValidationError):
            ms.clean()


class MatchScheduleFormTest(TestCase):
    """Phase 5: MatchScheduleForm tier-filtering and cross-tier validation."""

    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        Tier.objects.create(season=self.season, number=1, name='Tier 1')
        Tier.objects.create(season=self.season, number=2, name='Tier 2')
        self.p1 = User.objects.create_user(username='player1')
        self.p2 = User.objects.create_user(username='player2')
        self.p3 = User.objects.create_user(username='player3')
        SeasonPlayer.objects.create(season=self.season, player=self.p1, tier=1, is_active=True)
        SeasonPlayer.objects.create(season=self.season, player=self.p2, tier=1, is_active=True)
        SeasonPlayer.objects.create(season=self.season, player=self.p3, tier=2, is_active=True)

    def _form(self, player1, player2, tier, **extra):
        data = {
            'player1': player1.pk,
            'player2': player2.pk,
            'tier': tier,
        }
        data.update(extra)
        return MatchScheduleForm(data=data, season=self.season, tier=tier)

    def test_same_tier_match_is_valid(self):
        form = self._form(self.p1, self.p2, tier=1)
        self.assertTrue(form.is_valid(), form.errors)

    def test_cross_tier_match_is_invalid(self):
        form = self._form(self.p1, self.p3, tier=1)
        self.assertFalse(form.is_valid())

    def test_cross_tier_error_on_player2_field(self):
        # Use no tier kwarg so the dropdown isn't pre-filtered — then clean()
        # still enforces the cross-tier rule.
        data = {'player1': self.p1.pk, 'player2': self.p3.pk, 'tier': 1}
        form = MatchScheduleForm(data=data, season=self.season)
        form.is_valid()
        self.assertIn('player2', form.errors)

    def test_player_dropdowns_filtered_to_tier(self):
        form = MatchScheduleForm(season=self.season, tier=1)
        qs = form.fields['player1'].queryset
        self.assertIn(self.p1, qs)
        self.assertIn(self.p2, qs)
        self.assertNotIn(self.p3, qs)

    def test_tier_2_dropdown_shows_tier_2_players(self):
        form = MatchScheduleForm(season=self.season, tier=2)
        qs = form.fields['player1'].queryset
        self.assertIn(self.p3, qs)
        self.assertNotIn(self.p1, qs)
        self.assertNotIn(self.p2, qs)

    def test_inactive_players_excluded_from_dropdown(self):
        inactive = User.objects.create_user(username='inactive')
        SeasonPlayer.objects.create(season=self.season, player=inactive, tier=1, is_active=False)
        form = MatchScheduleForm(season=self.season, tier=1)
        qs = form.fields['player1'].queryset
        self.assertNotIn(inactive, qs)

    def test_no_season_does_not_filter(self):
        """Without a season, form still instantiates without error."""
        form = MatchScheduleForm()
        self.assertIsNotNone(form.fields['player1'])

    def test_tier_field_hidden_when_tier_kwarg_provided(self):
        from django.forms import HiddenInput
        form = MatchScheduleForm(season=self.season, tier=1)
        self.assertIsInstance(form.fields['tier'].widget, HiddenInput)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 — View tests
# ─────────────────────────────────────────────────────────────────────────────

class MatchupsViewTest(TestCase):
    """Phase 7: MatchupsView — upcoming/postponed matches for a season."""

    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.p1 = User.objects.create_user(username='player1')
        self.p2 = User.objects.create_user(username='player2')
        self.url = reverse('leagues:matchups', kwargs={'slug': self.season.slug})

    def _match(self, **kwargs):
        defaults = dict(season=self.season, player1=self.p1, player2=self.p2)
        defaults.update(kwargs)
        return Match.objects.create(**defaults)

    def test_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_404_for_invalid_season(self):
        response = self.client.get(reverse('leagues:matchups', kwargs={'slug': 'nonexistent-season'}))
        self.assertEqual(response.status_code, 404)

    def test_shows_scheduled_match(self):
        self._match(status=Match.STATUS_SCHEDULED)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 1)

    def test_shows_postponed_match(self):
        self._match(status=Match.STATUS_POSTPONED)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 1)

    def test_excludes_completed_match(self):
        self._match(status=Match.STATUS_COMPLETED)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 0)

    def test_excludes_walkover_match(self):
        self._match(status=Match.STATUS_WALKOVER)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 0)

    def test_shows_pending_match(self):
        self._match(status=Match.STATUS_PENDING)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 1)

    def test_excludes_cancelled_match(self):
        self._match(status=Match.STATUS_CANCELLED)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 0)

    def test_excludes_other_season_matches(self):
        other = Season.objects.create(name='Fall', year=2025)
        Match.objects.create(
            season=other, player1=self.p1, player2=self.p2,
            status=Match.STATUS_SCHEDULED,
        )
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 0)

    def test_single_tier_multi_tier_false(self):
        response = self.client.get(self.url)
        self.assertFalse(response.context['multi_tier'])

    def test_multi_tier_season_has_tier_tabs(self):
        Tier.objects.create(season=self.season, number=1, name='Tier 1')
        Tier.objects.create(season=self.season, number=2, name='Tier 2')
        response = self.client.get(self.url)
        self.assertTrue(response.context['multi_tier'])
        self.assertEqual(len(response.context['tiers']), 2)

    def test_multi_tier_matches_grouped_by_tier(self):
        Tier.objects.create(season=self.season, number=1, name='Tier 1')
        Tier.objects.create(season=self.season, number=2, name='Tier 2')
        p3 = User.objects.create_user(username='player3')
        p4 = User.objects.create_user(username='player4')
        self._match(tier=1, status=Match.STATUS_SCHEDULED)
        Match.objects.create(
            season=self.season, player1=p3, player2=p4,
            tier=2, status=Match.STATUS_SCHEDULED,
        )
        response = self.client.get(self.url)
        tiers = response.context['tiers']
        tier1_num, _, tier1_matches = tiers[0]
        tier2_num, _, tier2_matches = tiers[1]
        self.assertEqual(tier1_num, 1)
        self.assertEqual(tier2_num, 2)
        self.assertEqual(tier1_matches.count(), 1)
        self.assertEqual(tier2_matches.count(), 1)

    def test_ordered_by_scheduled_date_ascending(self):
        import datetime
        self._match(status=Match.STATUS_SCHEDULED, scheduled_date=datetime.date(2025, 6, 10))
        self._match(status=Match.STATUS_SCHEDULED, scheduled_date=datetime.date(2025, 6, 1))
        self._match(status=Match.STATUS_SCHEDULED, scheduled_date=datetime.date(2025, 6, 5))
        response = self.client.get(self.url)
        _, _, matches = response.context['tiers'][0]
        dates = [m.scheduled_date for m in matches]
        self.assertEqual(dates, sorted(dates))

    def test_uses_matchups_template(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'matches/matchups.html')


class MatchupsDisplayFilterTest(TestCase):
    """Tests for Season.schedule_display_mode filtering in MatchupsView."""

    def setUp(self):
        self.season = Season.objects.create(name='Filter', year=2025)
        self.p1 = User.objects.create_user(username='df_p1')
        self.p2 = User.objects.create_user(username='df_p2')
        self.url = reverse('leagues:matchups', kwargs={'slug': self.season.slug})
        self.today = datetime.date.today()

    def _match(self, **kwargs):
        defaults = dict(season=self.season, player1=self.p1, player2=self.p2, status=Match.STATUS_SCHEDULED)
        defaults.update(kwargs)
        return Match.objects.create(**defaults)

    def _count(self):
        _, _, matches = self.client.get(self.url).context['tiers'][0]
        return matches.count()

    def _set_mode(self, mode, days=None):
        self.season.schedule_display_mode = mode
        if days is not None:
            self.season.schedule_display_days = days
        self.season.save()

    # ── Default values ────────────────────────────────────────────────────────

    def test_display_mode_defaults_to_all(self):
        self.assertEqual(self.season.schedule_display_mode, Season.DISPLAY_ALL)

    def test_display_days_defaults_to_7(self):
        self.assertEqual(self.season.schedule_display_days, 7)

    # ── DISPLAY_ALL ───────────────────────────────────────────────────────────

    def test_all_shows_far_future_match(self):
        self._match(scheduled_date=self.today + datetime.timedelta(days=60))
        self.assertEqual(self._count(), 1)

    def test_all_shows_past_unplayed_match(self):
        self._match(scheduled_date=self.today - datetime.timedelta(days=30))
        self.assertEqual(self._count(), 1)

    # ── DISPLAY_CURRENT_DAY ───────────────────────────────────────────────────

    def test_current_day_shows_todays_match(self):
        self._set_mode(Season.DISPLAY_CURRENT_DAY)
        self._match(scheduled_date=self.today)
        self.assertEqual(self._count(), 1)

    def test_current_day_shows_past_unplayed_match(self):
        self._set_mode(Season.DISPLAY_CURRENT_DAY)
        self._match(scheduled_date=self.today - datetime.timedelta(days=5))
        self.assertEqual(self._count(), 1)

    def test_current_day_hides_tomorrows_match(self):
        self._set_mode(Season.DISPLAY_CURRENT_DAY)
        self._match(scheduled_date=self.today + datetime.timedelta(days=1))
        self.assertEqual(self._count(), 0)

    def test_current_day_shows_undated_match(self):
        self._set_mode(Season.DISPLAY_CURRENT_DAY)
        self._match(scheduled_date=None)
        self.assertEqual(self._count(), 1)

    def test_current_day_applies_to_postponed_status(self):
        self._set_mode(Season.DISPLAY_CURRENT_DAY)
        self._match(status=Match.STATUS_POSTPONED, scheduled_date=self.today - datetime.timedelta(days=1))
        self.assertEqual(self._count(), 1)

    def test_current_day_applies_to_pending_status_within_day(self):
        self._set_mode(Season.DISPLAY_CURRENT_DAY)
        self._match(status=Match.STATUS_PENDING, scheduled_date=self.today)
        self.assertEqual(self._count(), 1)

    def test_current_day_hides_pending_match_scheduled_tomorrow(self):
        self._set_mode(Season.DISPLAY_CURRENT_DAY)
        self._match(status=Match.STATUS_PENDING, scheduled_date=self.today + datetime.timedelta(days=1))
        self.assertEqual(self._count(), 0)

    # ── DISPLAY_CURRENT_WEEK ──────────────────────────────────────────────────

    def test_current_week_shows_todays_match(self):
        self._set_mode(Season.DISPLAY_CURRENT_WEEK)
        self._match(scheduled_date=self.today)
        self.assertEqual(self._count(), 1)

    def test_current_week_shows_match_on_sunday(self):
        self._set_mode(Season.DISPLAY_CURRENT_WEEK)
        week_end = self.today + datetime.timedelta(days=6 - self.today.weekday())
        self._match(scheduled_date=week_end)
        self.assertEqual(self._count(), 1)

    def test_current_week_shows_past_unplayed_match(self):
        self._set_mode(Season.DISPLAY_CURRENT_WEEK)
        self._match(scheduled_date=self.today - datetime.timedelta(days=10))
        self.assertEqual(self._count(), 1)

    def test_current_week_hides_next_week_match(self):
        self._set_mode(Season.DISPLAY_CURRENT_WEEK)
        days_to_next_monday = 7 - self.today.weekday()
        self._match(scheduled_date=self.today + datetime.timedelta(days=days_to_next_monday))
        self.assertEqual(self._count(), 0)

    def test_current_week_shows_undated_match(self):
        self._set_mode(Season.DISPLAY_CURRENT_WEEK)
        self._match(scheduled_date=None)
        self.assertEqual(self._count(), 1)

    # ── DISPLAY_NEXT_X_DAYS ───────────────────────────────────────────────────

    def test_next_x_days_shows_match_on_cutoff_date(self):
        self._set_mode(Season.DISPLAY_NEXT_X_DAYS, days=7)
        self._match(scheduled_date=self.today + datetime.timedelta(days=7))
        self.assertEqual(self._count(), 1)

    def test_next_x_days_hides_match_beyond_cutoff(self):
        self._set_mode(Season.DISPLAY_NEXT_X_DAYS, days=7)
        self._match(scheduled_date=self.today + datetime.timedelta(days=8))
        self.assertEqual(self._count(), 0)

    def test_next_x_days_shows_past_unplayed_match(self):
        self._set_mode(Season.DISPLAY_NEXT_X_DAYS, days=7)
        self._match(scheduled_date=self.today - datetime.timedelta(days=30))
        self.assertEqual(self._count(), 1)

    def test_next_x_days_respects_custom_window(self):
        self._set_mode(Season.DISPLAY_NEXT_X_DAYS, days=14)
        self._match(scheduled_date=self.today + datetime.timedelta(days=14))
        self._match(scheduled_date=self.today + datetime.timedelta(days=15))
        self.assertEqual(self._count(), 1)

    def test_next_x_days_shows_undated_match(self):
        self._set_mode(Season.DISPLAY_NEXT_X_DAYS, days=7)
        self._match(scheduled_date=None)
        self.assertEqual(self._count(), 1)


class ResultsViewTest(TestCase):
    """Phase 7: ResultsView — completed/walkover matches for a season."""

    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.p1 = User.objects.create_user(username='player1')
        self.p2 = User.objects.create_user(username='player2')
        self.url = reverse('leagues:results', kwargs={'slug': self.season.slug})

    def _match(self, **kwargs):
        defaults = dict(season=self.season, player1=self.p1, player2=self.p2)
        defaults.update(kwargs)
        return Match.objects.create(**defaults)

    def test_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_404_for_invalid_season(self):
        response = self.client.get(reverse('leagues:results', kwargs={'slug': 'nonexistent-season'}))
        self.assertEqual(response.status_code, 404)

    def test_shows_completed_match(self):
        self._match(status=Match.STATUS_COMPLETED, winner=self.p1)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 1)

    def test_shows_walkover_match(self):
        self._match(status=Match.STATUS_WALKOVER, winner=self.p1)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 1)

    def test_excludes_scheduled_match(self):
        self._match(status=Match.STATUS_SCHEDULED)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 0)

    def test_excludes_pending_match(self):
        self._match(status=Match.STATUS_PENDING)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 0)

    def test_excludes_postponed_match(self):
        self._match(status=Match.STATUS_POSTPONED)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 0)

    def test_excludes_cancelled_match(self):
        self._match(status=Match.STATUS_CANCELLED)
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 0)

    def test_excludes_other_season_matches(self):
        other = Season.objects.create(name='Fall', year=2025)
        Match.objects.create(
            season=other, player1=self.p1, player2=self.p2,
            status=Match.STATUS_COMPLETED, winner=self.p1,
        )
        response = self.client.get(self.url)
        tier_num, _, matches = response.context['tiers'][0]
        self.assertEqual(matches.count(), 0)

    def test_single_tier_multi_tier_false(self):
        response = self.client.get(self.url)
        self.assertFalse(response.context['multi_tier'])

    def test_multi_tier_season_has_tier_tabs(self):
        Tier.objects.create(season=self.season, number=1, name='Tier 1')
        Tier.objects.create(season=self.season, number=2, name='Tier 2')
        response = self.client.get(self.url)
        self.assertTrue(response.context['multi_tier'])
        self.assertEqual(len(response.context['tiers']), 2)

    def test_ordered_by_played_date_descending(self):
        import datetime
        self._match(status=Match.STATUS_COMPLETED, winner=self.p1, played_date=datetime.date(2025, 5, 1))
        self._match(status=Match.STATUS_COMPLETED, winner=self.p1, played_date=datetime.date(2025, 5, 15))
        self._match(status=Match.STATUS_COMPLETED, winner=self.p1, played_date=datetime.date(2025, 5, 8))
        response = self.client.get(self.url)
        _, _, matches = response.context['tiers'][0]
        dates = [m.played_date for m in matches]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_walkover_with_no_played_date_sorts_last(self):
        """Walkovers with no played_date should not float to the top."""
        import datetime
        self._match(status=Match.STATUS_COMPLETED, winner=self.p1, played_date=datetime.date(2025, 5, 1))
        self._match(status=Match.STATUS_WALKOVER, winner=self.p1, played_date=None)
        response = self.client.get(self.url)
        _, _, matches = response.context['tiers'][0]
        match_list = list(matches)
        self.assertEqual(match_list[0].status, Match.STATUS_COMPLETED)
        self.assertEqual(match_list[1].status, Match.STATUS_WALKOVER)

    def test_multi_tier_season_groups_results(self):
        Tier.objects.create(season=self.season, number=1, name='Tier 1')
        Tier.objects.create(season=self.season, number=2, name='Tier 2')
        p3 = User.objects.create_user(username='player3')
        p4 = User.objects.create_user(username='player4')
        self._match(tier=1, status=Match.STATUS_COMPLETED, winner=self.p1)
        Match.objects.create(
            season=self.season, player1=p3, player2=p4,
            tier=2, status=Match.STATUS_WALKOVER, winner=p3,
        )
        response = self.client.get(self.url)
        tiers = response.context['tiers']
        self.assertEqual(len(tiers), 2)
        self.assertEqual(tiers[0][2].count(), 1)
        self.assertEqual(tiers[1][2].count(), 1)

    def test_uses_results_template(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'matches/results.html')


class MatchDetailViewTest(TestCase):
    """Phase 7: MatchDetailView — individual match with set scores."""

    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.p1 = User.objects.create_user(username='player1')
        self.p2 = User.objects.create_user(username='player2')
        self.match = Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            status=Match.STATUS_COMPLETED, winner=self.p1,
        )
        self.url = reverse('matches:match_detail', kwargs={'pk': self.match.pk})

    def test_returns_200(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_404_for_invalid_match(self):
        response = self.client.get(reverse('matches:match_detail', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 404)

    def test_context_contains_match(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['match'], self.match)

    def test_context_contains_season(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['season'], self.season)

    def test_context_multi_tier_false_for_single_tier(self):
        response = self.client.get(self.url)
        self.assertFalse(response.context['multi_tier'])

    def test_context_multi_tier_true_for_multi_tier_season(self):
        Tier.objects.create(season=self.season, number=1, name='Tier 1')
        Tier.objects.create(season=self.season, number=2, name='Tier 2')
        response = self.client.get(self.url)
        self.assertTrue(response.context['multi_tier'])

    def test_context_contains_sets(self):
        MatchSet.objects.create(
            match=self.match, set_number=1, player1_games=6, player2_games=3,
        )
        MatchSet.objects.create(
            match=self.match, set_number=2, player1_games=6, player2_games=4,
        )
        response = self.client.get(self.url)
        self.assertEqual(response.context['sets'].count(), 2)

    def test_uses_match_detail_template(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'matches/match_detail.html')

    def test_completed_match_back_link_goes_to_results(self):
        response = self.client.get(self.url)
        results_url = reverse('leagues:results', kwargs={'slug': self.season.slug})
        self.assertContains(response, results_url)

    def test_scheduled_match_back_link_goes_to_matchups(self):
        scheduled = Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            status=Match.STATUS_SCHEDULED,
        )
        response = self.client.get(reverse('matches:match_detail', kwargs={'pk': scheduled.pk}))
        matchups_url = reverse('leagues:matchups', kwargs={'slug': self.season.slug})
        self.assertContains(response, matchups_url)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 — ResultEntryForm tests
# ─────────────────────────────────────────────────────────────────────────────

class ResultEntryFormValidScoresTest(TestCase):
    """Valid set-score combinations are accepted."""

    def setUp(self):
        self.season = Season.objects.create(
            name='Spring', year=2025, sets_to_win=2,
            final_set_format=Season.FINAL_SET_FULL,
        )
        self.p1 = User.objects.create_user(username='p1')
        self.p2 = User.objects.create_user(username='p2')
        self.match = Match.objects.create(season=self.season, player1=self.p1, player2=self.p2)

    def _form(self, data):
        return ResultEntryForm(data=data, match=self.match)

    def test_2_0_straight_sets(self):
        form = self._form({'set1_p1': 6, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 4})
        self.assertTrue(form.is_valid(), form.errors)

    def test_2_1_three_sets(self):
        form = self._form({
            'set1_p1': 6, 'set1_p2': 3,
            'set2_p1': 3, 'set2_p2': 6,
            'set3_p1': 6, 'set3_p2': 4,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_7_5_set_is_valid(self):
        form = self._form({'set1_p1': 7, 'set1_p2': 5, 'set2_p1': 6, 'set2_p2': 3})
        self.assertTrue(form.is_valid(), form.errors)

    def test_7_6_with_tiebreak(self):
        form = self._form({
            'set1_p1': 7, 'set1_p2': 6,
            'set1_tb_p1': 7, 'set1_tb_p2': 4,
            'set2_p1': 6, 'set2_p2': 3,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_p2_wins_straight_sets(self):
        form = self._form({'set1_p1': 3, 'set1_p2': 6, 'set2_p1': 2, 'set2_p2': 6})
        self.assertTrue(form.is_valid(), form.errors)


class ResultEntryFormInvalidScoresTest(TestCase):
    """Invalid set-score combinations are rejected."""

    def setUp(self):
        self.season = Season.objects.create(
            name='Spring', year=2025, sets_to_win=2,
            final_set_format=Season.FINAL_SET_FULL,
        )
        self.p1 = User.objects.create_user(username='p1')
        self.p2 = User.objects.create_user(username='p2')
        self.match = Match.objects.create(season=self.season, player1=self.p1, player2=self.p2)

    def _form(self, data):
        return ResultEntryForm(data=data, match=self.match)

    def test_empty_form_invalid(self):
        form = self._form({})
        self.assertFalse(form.is_valid())

    def test_too_few_games_invalid(self):
        form = self._form({'set1_p1': 5, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 3})
        self.assertFalse(form.is_valid())

    def test_winner_leads_by_one_invalid(self):
        form = self._form({'set1_p1': 6, 'set1_p2': 5, 'set2_p1': 6, 'set2_p2': 3})
        self.assertFalse(form.is_valid())

    def test_7_6_without_tiebreak_invalid(self):
        form = self._form({'set1_p1': 7, 'set1_p2': 6, 'set2_p1': 6, 'set2_p2': 3})
        self.assertFalse(form.is_valid())

    def test_tiebreak_on_non_76_invalid(self):
        form = self._form({
            'set1_p1': 6, 'set1_p2': 3,
            'set1_tb_p1': 7, 'set1_tb_p2': 3,
            'set2_p1': 6, 'set2_p2': 4,
        })
        self.assertFalse(form.is_valid())

    def test_extra_set_after_match_decided_invalid(self):
        # Match decided in 2 sets, but a 3rd set is also entered
        form = self._form({
            'set1_p1': 6, 'set1_p2': 3,
            'set2_p1': 6, 'set2_p2': 3,
            'set3_p1': 6, 'set3_p2': 3,
        })
        self.assertFalse(form.is_valid())

    def test_incomplete_match_invalid(self):
        # Only 1 set entered in best-of-3 — neither player has won 2
        form = self._form({'set1_p1': 6, 'set1_p2': 3})
        self.assertFalse(form.is_valid())

    def test_gap_in_sets_invalid(self):
        # Set 2 missing; set 3 filled (for a best-of-3)
        form = self._form({
            'set1_p1': 6, 'set1_p2': 3,
            'set3_p1': 6, 'set3_p2': 4,
        })
        self.assertFalse(form.is_valid())

    def test_tiebreak_winner_mismatch_invalid(self):
        # Player 1 wins 7-6 but tiebreak gives p2 more points
        form = self._form({
            'set1_p1': 7, 'set1_p2': 6,
            'set1_tb_p1': 4, 'set1_tb_p2': 7,
            'set2_p1': 6, 'set2_p2': 3,
        })
        self.assertFalse(form.is_valid())


class ResultEntryFormTiebreakFinalSetTest(TestCase):
    """Deciding set with final_set_format='tiebreak' must be 7-6."""

    def setUp(self):
        self.season = Season.objects.create(
            name='Spring', year=2025, sets_to_win=2,
            final_set_format=Season.FINAL_SET_TIEBREAK,
        )
        self.p1 = User.objects.create_user(username='p1')
        self.p2 = User.objects.create_user(username='p2')
        self.match = Match.objects.create(season=self.season, player1=self.p1, player2=self.p2)

    def _form(self, data):
        return ResultEntryForm(data=data, match=self.match)

    def test_76_deciding_set_valid(self):
        form = self._form({
            'set1_p1': 6, 'set1_p2': 3,
            'set2_p1': 3, 'set2_p2': 6,
            'set3_p1': 7, 'set3_p2': 6,
            'set3_tb_p1': 7, 'set3_tb_p2': 4,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_non_76_deciding_set_invalid(self):
        form = self._form({
            'set1_p1': 6, 'set1_p2': 3,
            'set2_p1': 3, 'set2_p2': 6,
            'set3_p1': 6, 'set3_p2': 4,
        })
        self.assertFalse(form.is_valid())


class ResultEntryFormSuperTiebreaKTest(TestCase):
    """Deciding set with final_set_format='super' uses 10-point tiebreak."""

    def setUp(self):
        self.season = Season.objects.create(
            name='Spring', year=2025, sets_to_win=2,
            final_set_format=Season.FINAL_SET_SUPER,
        )
        self.p1 = User.objects.create_user(username='p1')
        self.p2 = User.objects.create_user(username='p2')
        self.match = Match.objects.create(season=self.season, player1=self.p1, player2=self.p2)

    def _form(self, data):
        return ResultEntryForm(data=data, match=self.match)

    def test_super_tiebreak_10_5_valid(self):
        # Sets 1 and 2 split, super tiebreak in set 3
        form = self._form({
            'set1_p1': 6, 'set1_p2': 3,
            'set2_p1': 3, 'set2_p2': 6,
            'set3_p1': 10, 'set3_p2': 5,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_super_tiebreak_less_than_10_invalid(self):
        form = self._form({
            'set1_p1': 6, 'set1_p2': 3,
            'set2_p1': 3, 'set2_p2': 6,
            'set3_p1': 9, 'set3_p2': 5,
        })
        self.assertFalse(form.is_valid())

    def test_super_tiebreak_lead_by_one_invalid(self):
        form = self._form({
            'set1_p1': 6, 'set1_p2': 3,
            'set2_p1': 3, 'set2_p2': 6,
            'set3_p1': 10, 'set3_p2': 9,
        })
        self.assertFalse(form.is_valid())

    def test_super_tiebreak_extended_11_9_valid(self):
        form = self._form({
            'set1_p1': 6, 'set1_p2': 3,
            'set2_p1': 3, 'set2_p2': 6,
            'set3_p1': 11, 'set3_p2': 9,
        })
        self.assertTrue(form.is_valid(), form.errors)


class ResultEntryFormBestOf5Test(TestCase):
    """Best-of-5 (sets_to_win=3) match score validation."""

    def setUp(self):
        self.season = Season.objects.create(
            name='Spring', year=2025, sets_to_win=3,
            final_set_format=Season.FINAL_SET_FULL,
        )
        self.p1 = User.objects.create_user(username='p1')
        self.p2 = User.objects.create_user(username='p2')
        self.match = Match.objects.create(season=self.season, player1=self.p1, player2=self.p2)

    def _form(self, data):
        return ResultEntryForm(data=data, match=self.match)

    def test_3_0_valid(self):
        form = self._form({
            'set1_p1': 6, 'set1_p2': 2,
            'set2_p1': 6, 'set2_p2': 3,
            'set3_p1': 6, 'set3_p2': 4,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_3_2_valid(self):
        form = self._form({
            'set1_p1': 6, 'set1_p2': 3,
            'set2_p1': 3, 'set2_p2': 6,
            'set3_p1': 6, 'set3_p2': 4,
            'set4_p1': 4, 'set4_p2': 6,
            'set5_p1': 6, 'set5_p2': 2,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_max_sets_generates_5_sets(self):
        form = ResultEntryForm(match=self.match)
        self.assertEqual(form.max_sets, 5)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 — EnterResultView tests
# ─────────────────────────────────────────────────────────────────────────────

class EnterResultViewGetTest(TestCase):
    """GET requests to EnterResultView."""

    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025, sets_to_win=2)
        self.p1 = User.objects.create_user(username='p1', password='pass')
        self.p2 = User.objects.create_user(username='p2', password='pass')
        self.match = Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            status=Match.STATUS_SCHEDULED,
        )
        self.url = reverse('matches:enter_result', kwargs={'pk': self.match.pk})

    def test_anonymous_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_player1_can_access(self):
        self.client.login(username='p1', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_player2_can_access(self):
        self.client.login(username='p2', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_unrelated_user_gets_403(self):
        other = User.objects.create_user(username='other', password='pass')
        self.client.login(username='other', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_uses_enter_result_template(self):
        self.client.login(username='p1', password='pass')
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'matches/enter_result.html')

    def test_context_has_form_and_match(self):
        self.client.login(username='p1', password='pass')
        response = self.client.get(self.url)
        self.assertIn('form', response.context)
        self.assertEqual(response.context['match'], self.match)

    def test_completed_match_redirects(self):
        self.match.status = Match.STATUS_COMPLETED
        self.match.save()
        self.client.login(username='p1', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)


class EnterResultViewPostTest(TestCase):
    """POST requests to EnterResultView."""

    def setUp(self):
        self.season = Season.objects.create(
            name='Spring', year=2025, sets_to_win=2,
            final_set_format=Season.FINAL_SET_FULL,
        )
        self.p1 = User.objects.create_user(username='p1', password='pass')
        self.p2 = User.objects.create_user(username='p2', password='pass')
        self.match = Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            status=Match.STATUS_SCHEDULED,
        )
        self.url = reverse('matches:enter_result', kwargs={'pk': self.match.pk})
        self.client.login(username='p1', password='pass')

    def _post(self, data):
        return self.client.post(self.url, data)

    def test_valid_submission_creates_sets(self):
        self._post({'set1_p1': 6, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 4})
        self.assertEqual(self.match.sets.count(), 2)

    def test_valid_submission_sets_status_pending(self):
        self._post({'set1_p1': 6, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 4})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_PENDING)

    def test_valid_submission_sets_entered_by(self):
        self._post({'set1_p1': 6, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 4})
        self.match.refresh_from_db()
        self.assertEqual(self.match.entered_by, self.p1)

    def test_valid_submission_redirects_to_match_detail(self):
        response = self._post({'set1_p1': 6, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 4})
        self.assertRedirects(
            response,
            reverse('matches:match_detail', kwargs={'pk': self.match.pk}),
        )

    def test_set_scores_stored_correctly(self):
        self._post({'set1_p1': 6, 'set1_p2': 3, 'set2_p1': 7, 'set2_p2': 5})
        sets = list(self.match.sets.order_by('set_number'))
        self.assertEqual(sets[0].player1_games, 6)
        self.assertEqual(sets[0].player2_games, 3)
        self.assertEqual(sets[1].player1_games, 7)
        self.assertEqual(sets[1].player2_games, 5)

    def test_tiebreak_scores_stored_correctly(self):
        self._post({
            'set1_p1': 7, 'set1_p2': 6,
            'set1_tb_p1': 7, 'set1_tb_p2': 4,
            'set2_p1': 6, 'set2_p2': 3,
        })
        s1 = self.match.sets.get(set_number=1)
        self.assertEqual(s1.tiebreak_player1_points, 7)
        self.assertEqual(s1.tiebreak_player2_points, 4)

    def test_invalid_submission_rerenders_form(self):
        response = self._post({'set1_p1': 5, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 3})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'matches/enter_result.html')

    def test_invalid_submission_does_not_change_status(self):
        self._post({'set1_p1': 5, 'set1_p2': 3})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_SCHEDULED)

    def test_player2_can_submit(self):
        self.client.login(username='p2', password='pass')
        self._post({'set1_p1': 6, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 4})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_PENDING)

    def test_staff_can_submit(self):
        staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.client.login(username='staff', password='pass')
        self.client.post(self.url, {'set1_p1': 6, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 4})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_COMPLETED)

    def test_admin_submission_auto_confirms(self):
        staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.client.login(username='staff', password='pass')
        self.client.post(self.url, {'set1_p1': 6, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 4})
        self.match.refresh_from_db()
        self.assertEqual(self.match.confirmed_by, staff)
        self.assertIsNotNone(self.match.played_date)

    def test_admin_submission_sets_winner(self):
        staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.client.login(username='staff', password='pass')
        self.client.post(self.url, {'set1_p1': 6, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 4})
        self.match.refresh_from_db()
        self.assertEqual(self.match.winner, self.p1)

    def test_admin_submission_sets_winner_p2(self):
        staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.client.login(username='staff', password='pass')
        self.client.post(self.url, {'set1_p1': 3, 'set1_p2': 6, 'set2_p1': 4, 'set2_p2': 6})
        self.match.refresh_from_db()
        self.assertEqual(self.match.winner, self.p2)

    def test_non_admin_submission_stays_pending(self):
        self._post({'set1_p1': 6, 'set1_p2': 3, 'set2_p1': 6, 'set2_p2': 4})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_PENDING)
        self.assertIsNone(self.match.confirmed_by)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 — ConfirmResultView tests
# ─────────────────────────────────────────────────────────────────────────────

class ConfirmResultViewSetupMixin:
    """Shared setup: a pending match with two sets entered by p1."""

    def setUp(self):
        self.season = Season.objects.create(
            name='Spring', year=2025, sets_to_win=2,
            final_set_format=Season.FINAL_SET_FULL,
        )
        self.p1 = User.objects.create_user(username='p1', password='pass')
        self.p2 = User.objects.create_user(username='p2', password='pass')
        self.match = Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            status=Match.STATUS_PENDING, entered_by=self.p1,
        )
        MatchSet.objects.create(match=self.match, set_number=1, player1_games=6, player2_games=3)
        MatchSet.objects.create(match=self.match, set_number=2, player1_games=6, player2_games=4)
        self.url = reverse('matches:confirm_result', kwargs={'pk': self.match.pk})


class ConfirmResultViewGetTest(ConfirmResultViewSetupMixin, TestCase):
    """GET requests to ConfirmResultView."""

    def test_anonymous_redirects_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_opponent_can_access(self):
        self.client.login(username='p2', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_entered_by_player_gets_403(self):
        """The player who entered the score cannot confirm it."""
        self.client.login(username='p1', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_unrelated_user_gets_403(self):
        other = User.objects.create_user(username='other', password='pass')
        self.client.login(username='other', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_staff_can_access(self):
        staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.client.login(username='staff', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_non_pending_match_redirects(self):
        self.match.status = Match.STATUS_SCHEDULED
        self.match.save()
        self.client.login(username='p2', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_context_has_match_and_sets(self):
        self.client.login(username='p2', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.context['match'], self.match)
        self.assertEqual(response.context['sets'].count(), 2)

    def test_uses_confirm_result_template(self):
        self.client.login(username='p2', password='pass')
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'matches/confirm_result.html')


class ConfirmResultViewConfirmTest(ConfirmResultViewSetupMixin, TestCase):
    """POST action=confirm."""

    def _confirm(self):
        self.client.login(username='p2', password='pass')
        return self.client.post(self.url, {'action': 'confirm'})

    def test_entered_by_player_post_gets_403(self):
        """The player who entered cannot POST a confirmation either."""
        self.client.login(username='p1', password='pass')
        response = self.client.post(self.url, {'action': 'confirm'})
        self.assertEqual(response.status_code, 403)

    def test_confirm_sets_status_completed(self):
        self._confirm()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_COMPLETED)

    def test_confirm_sets_winner_correctly(self):
        """p1 won both sets (6-3, 6-4) so p1 should be winner."""
        self._confirm()
        self.match.refresh_from_db()
        self.assertEqual(self.match.winner, self.p1)

    def test_confirm_sets_confirmed_by(self):
        self._confirm()
        self.match.refresh_from_db()
        self.assertEqual(self.match.confirmed_by, self.p2)

    def test_confirm_sets_played_date_to_today(self):
        import datetime
        self._confirm()
        self.match.refresh_from_db()
        self.assertEqual(self.match.played_date, datetime.date.today())

    def test_confirm_redirects_to_match_detail(self):
        response = self._confirm()
        self.assertRedirects(
            response,
            reverse('matches:match_detail', kwargs={'pk': self.match.pk}),
        )

    def test_confirm_p2_winner(self):
        """When p2 wins more sets, p2 is the winner."""
        self.match.sets.all().delete()
        MatchSet.objects.create(match=self.match, set_number=1, player1_games=3, player2_games=6)
        MatchSet.objects.create(match=self.match, set_number=2, player1_games=4, player2_games=6)
        self._confirm()
        self.match.refresh_from_db()
        self.assertEqual(self.match.winner, self.p2)

    def test_staff_can_confirm(self):
        staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.client.login(username='staff', password='pass')
        self.client.post(self.url, {'action': 'confirm'})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_COMPLETED)

    def test_tied_sets_does_not_complete_match(self):
        """If sets are somehow tied, confirm redirects without completing the match."""
        self.match.sets.all().delete()
        MatchSet.objects.create(match=self.match, set_number=1, player1_games=6, player2_games=3)
        MatchSet.objects.create(match=self.match, set_number=2, player1_games=3, player2_games=6)
        self._confirm()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_PENDING)


class ConfirmResultViewDisputeTest(ConfirmResultViewSetupMixin, TestCase):
    """POST action=dispute."""

    def _dispute(self):
        self.client.login(username='p2', password='pass')
        return self.client.post(self.url, {'action': 'dispute'})

    def test_dispute_resets_status_to_scheduled(self):
        self._dispute()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_SCHEDULED)

    def test_dispute_deletes_sets(self):
        self._dispute()
        self.assertEqual(self.match.sets.count(), 0)

    def test_dispute_clears_entered_by(self):
        self._dispute()
        self.match.refresh_from_db()
        self.assertIsNone(self.match.entered_by)

    def test_dispute_redirects_to_match_detail(self):
        response = self._dispute()
        self.assertRedirects(
            response,
            reverse('matches:match_detail', kwargs={'pk': self.match.pk}),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10 — WalkoverForm tests
# ─────────────────────────────────────────────────────────────────────────────

class WalkoverFormTest(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.p1 = User.objects.create_user(username='p1', first_name='Alice', last_name='Smith')
        self.p2 = User.objects.create_user(username='p2', first_name='Bob', last_name='Jones')
        self.match = Match.objects.create(season=self.season, player1=self.p1, player2=self.p2)

    def _form(self, winner, reason=''):
        return WalkoverForm(data={'winner': winner, 'reason': reason}, match=self.match)

    def test_player1_wins_valid(self):
        form = self._form(WalkoverForm.WINNER_P1)
        self.assertTrue(form.is_valid(), form.errors)

    def test_player2_wins_valid(self):
        form = self._form(WalkoverForm.WINNER_P2)
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_winner_invalid(self):
        form = WalkoverForm(data={'reason': 'no show'}, match=self.match)
        self.assertFalse(form.is_valid())
        self.assertIn('winner', form.errors)

    def test_invalid_winner_choice_rejected(self):
        form = self._form('player3')
        self.assertFalse(form.is_valid())

    def test_reason_optional(self):
        form = WalkoverForm(data={'winner': WalkoverForm.WINNER_P1}, match=self.match)
        self.assertTrue(form.is_valid(), form.errors)

    def test_winner_choices_show_player_names(self):
        form = WalkoverForm(match=self.match)
        choice_labels = [label for _, label in form.fields['winner'].choices]
        self.assertIn('Alice Smith', choice_labels)
        self.assertIn('Bob Jones', choice_labels)

    def test_winner_choices_fall_back_to_username(self):
        p3 = User.objects.create_user(username='noname')
        p4 = User.objects.create_user(username='alsononame')
        match = Match.objects.create(season=self.season, player1=p3, player2=p4)
        form = WalkoverForm(match=match)
        choice_labels = [label for _, label in form.fields['winner'].choices]
        self.assertIn('noname', choice_labels)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10 — PostponeForm tests
# ─────────────────────────────────────────────────────────────────────────────

class PostponeFormTest(TestCase):
    def _form(self, date, reason=''):
        return PostponeForm(data={'new_date': date.isoformat(), 'reason': reason})

    def test_future_date_valid(self):
        form = self._form(datetime.date.today() + datetime.timedelta(days=7))
        self.assertTrue(form.is_valid(), form.errors)

    def test_today_valid(self):
        form = self._form(datetime.date.today())
        self.assertTrue(form.is_valid(), form.errors)

    def test_past_date_invalid(self):
        form = self._form(datetime.date.today() - datetime.timedelta(days=1))
        self.assertFalse(form.is_valid())
        self.assertIn('new_date', form.errors)

    def test_reason_optional(self):
        form = PostponeForm(data={'new_date': datetime.date.today().isoformat()})
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_date_invalid(self):
        form = PostponeForm(data={'reason': 'rain'})
        self.assertFalse(form.is_valid())
        self.assertIn('new_date', form.errors)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10 — WalkoverView tests
# ─────────────────────────────────────────────────────────────────────────────

class WalkoverViewSetupMixin:
    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.p1 = User.objects.create_user(username='p1', password='pass')
        self.p2 = User.objects.create_user(username='p2', password='pass')
        self.staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.match = Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            status=Match.STATUS_SCHEDULED,
        )
        self.url = reverse('matches:walkover', kwargs={'pk': self.match.pk})


class WalkoverViewGetTest(WalkoverViewSetupMixin, TestCase):
    def test_anonymous_redirects(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_unrelated_user_gets_403(self):
        other = User.objects.create_user(username='other', password='pass')
        self.client.login(username='other', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_player1_can_access(self):
        self.client.login(username='p1', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_player2_can_access(self):
        self.client.login(username='p2', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_staff_can_access(self):
        self.client.login(username='staff', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_uses_walkover_template(self):
        self.client.login(username='p1', password='pass')
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'matches/walkover.html')

    def test_context_has_form_and_match(self):
        self.client.login(username='p1', password='pass')
        response = self.client.get(self.url)
        self.assertIn('form', response.context)
        self.assertEqual(response.context['match'], self.match)


class WalkoverViewPostTest(WalkoverViewSetupMixin, TestCase):
    def _post(self, winner=WalkoverForm.WINNER_P1, reason='', user='p1'):
        self.client.login(username=user, password='pass')
        return self.client.post(self.url, {'winner': winner, 'reason': reason})

    def test_sets_status_pending(self):
        self._post()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_PENDING)

    def test_sets_winner_player1(self):
        self._post(winner=WalkoverForm.WINNER_P1)
        self.match.refresh_from_db()
        self.assertEqual(self.match.winner, self.p1)

    def test_sets_winner_player2(self):
        self._post(winner=WalkoverForm.WINNER_P2)
        self.match.refresh_from_db()
        self.assertEqual(self.match.winner, self.p2)

    def test_sets_walkover_reason(self):
        self._post(reason='No show')
        self.match.refresh_from_db()
        self.assertEqual(self.match.walkover_reason, 'No show')

    def test_empty_reason_stored_as_empty_string(self):
        self._post(reason='')
        self.match.refresh_from_db()
        self.assertEqual(self.match.walkover_reason, '')

    def test_sets_entered_by(self):
        self._post(user='p1')
        self.match.refresh_from_db()
        self.assertEqual(self.match.entered_by, self.p1)

    def test_played_date_not_set_until_confirmed(self):
        self._post(user='p1')
        self.match.refresh_from_db()
        self.assertIsNone(self.match.played_date)

    def test_redirects_to_match_detail(self):
        response = self._post()
        self.assertRedirects(response, reverse('matches:match_detail', kwargs={'pk': self.match.pk}))

    def test_player2_can_submit(self):
        self._post(user='p2')
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_PENDING)

    def test_staff_can_submit(self):
        self._post(user='staff')
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_WALKOVER)

    def test_admin_walkover_auto_confirms(self):
        self._post(user='staff')
        self.match.refresh_from_db()
        self.assertEqual(self.match.confirmed_by, self.staff)
        self.assertIsNotNone(self.match.played_date)

    def test_admin_walkover_sets_winner(self):
        self._post(winner=WalkoverForm.WINNER_P2, user='staff')
        self.match.refresh_from_db()
        self.assertEqual(self.match.winner, self.p2)

    def test_non_admin_walkover_stays_pending(self):
        self._post(user='p1')
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_PENDING)
        self.assertIsNone(self.match.confirmed_by)

    def test_invalid_form_rerenders(self):
        self.client.login(username='p1', password='pass')
        response = self.client.post(self.url, {'winner': 'invalid_choice'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'matches/walkover.html')

    def test_completed_match_rejected(self):
        self.match.status = Match.STATUS_COMPLETED
        self.match.winner = self.p1
        self.match.save()
        self._post()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_COMPLETED)

    def test_already_walkover_rejected(self):
        self.match.status = Match.STATUS_WALKOVER
        self.match.winner = self.p1
        self.match.save()
        self._post(winner=WalkoverForm.WINNER_P2)
        self.match.refresh_from_db()
        self.assertEqual(self.match.winner, self.p1)

    def test_postponed_match_accepted(self):
        self.match.status = Match.STATUS_POSTPONED
        self.match.save()
        self._post()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_PENDING)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10 — PostponeView tests
# ─────────────────────────────────────────────────────────────────────────────

class PostponeViewSetupMixin:
    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.p1 = User.objects.create_user(username='p1', password='pass')
        self.p2 = User.objects.create_user(username='p2', password='pass')
        self.staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.match = Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            status=Match.STATUS_SCHEDULED,
        )
        self.url = reverse('matches:postpone', kwargs={'pk': self.match.pk})
        self.future_date = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()


class PostponeViewGetTest(PostponeViewSetupMixin, TestCase):
    def test_anonymous_redirects(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_unrelated_user_gets_403(self):
        other = User.objects.create_user(username='other', password='pass')
        self.client.login(username='other', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_player1_can_access(self):
        self.client.login(username='p1', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_player2_can_access(self):
        self.client.login(username='p2', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_staff_can_access(self):
        self.client.login(username='staff', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_uses_postpone_template(self):
        self.client.login(username='p1', password='pass')
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'matches/postpone.html')

    def test_context_has_form_and_match(self):
        self.client.login(username='p1', password='pass')
        response = self.client.get(self.url)
        self.assertIn('form', response.context)
        self.assertEqual(response.context['match'], self.match)


class PostponeViewPostTest(PostponeViewSetupMixin, TestCase):
    def _post(self, date=None, reason='', user='p1'):
        self.client.login(username=user, password='pass')
        return self.client.post(self.url, {
            'new_date': date or self.future_date,
            'reason': reason,
        })

    def test_sets_status_postponed(self):
        self._post()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_POSTPONED)

    def test_sets_new_scheduled_date(self):
        new_date = datetime.date.today() + datetime.timedelta(days=14)
        self._post(date=new_date.isoformat())
        self.match.refresh_from_db()
        self.assertEqual(self.match.scheduled_date, new_date)

    def test_reason_appended_to_notes(self):
        self._post(reason='Rain delay')
        self.match.refresh_from_db()
        self.assertIn('Rain delay', self.match.notes)
        self.assertIn('Postponed:', self.match.notes)

    def test_reason_appended_to_existing_notes(self):
        self.match.notes = 'Previous note'
        self.match.save()
        self._post(reason='Injury')
        self.match.refresh_from_db()
        self.assertIn('Previous note', self.match.notes)
        self.assertIn('Injury', self.match.notes)

    def test_empty_reason_does_not_change_notes(self):
        self.match.notes = 'Original'
        self.match.save()
        self._post(reason='')
        self.match.refresh_from_db()
        self.assertEqual(self.match.notes, 'Original')

    def test_redirects_to_match_detail(self):
        response = self._post()
        self.assertRedirects(response, reverse('matches:match_detail', kwargs={'pk': self.match.pk}))

    def test_past_date_rerenders_form(self):
        past = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        response = self._post(date=past)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'matches/postpone.html')

    def test_past_date_does_not_change_status(self):
        past = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        self._post(date=past)
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_SCHEDULED)

    def test_player2_can_postpone(self):
        self._post(user='p2')
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_POSTPONED)

    def test_staff_can_postpone(self):
        self._post(user='staff')
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_POSTPONED)

    def test_completed_match_rejected(self):
        self.match.status = Match.STATUS_COMPLETED
        self.match.winner = self.p1
        self.match.save()
        self._post()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_COMPLETED)

    def test_walkover_match_rejected(self):
        self.match.status = Match.STATUS_WALKOVER
        self.match.winner = self.p1
        self.match.save()
        self._post()
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_WALKOVER)

    def test_already_postponed_match_can_be_rescheduled(self):
        self.match.status = Match.STATUS_POSTPONED
        self.match.save()
        new_date = datetime.date.today() + datetime.timedelta(days=21)
        self._post(date=new_date.isoformat())
        self.match.refresh_from_db()
        self.assertEqual(self.match.scheduled_date, new_date)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10 — Walkover confirmation (via ConfirmResultView) tests
# ─────────────────────────────────────────────────────────────────────────────

class WalkoverConfirmTest(TestCase):
    """Walkover submitted by player1, confirmed/disputed by player2."""

    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.p1 = User.objects.create_user(username='p1', password='pass')
        self.p2 = User.objects.create_user(username='p2', password='pass')
        self.match = Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            status=Match.STATUS_PENDING,
            entered_by=self.p1,
            winner=self.p1,
            walkover_reason='No show',
        )
        self.url = reverse('matches:confirm_result', kwargs={'pk': self.match.pk})

    def test_get_shows_is_walkover_true(self):
        self.client.login(username='p2', password='pass')
        response = self.client.get(self.url)
        self.assertTrue(response.context['is_walkover'])

    def test_get_shows_is_walkover_false_when_sets_exist(self):
        MatchSet.objects.create(match=self.match, set_number=1, player1_games=6, player2_games=3)
        MatchSet.objects.create(match=self.match, set_number=2, player1_games=6, player2_games=4)
        self.client.login(username='p2', password='pass')
        response = self.client.get(self.url)
        self.assertFalse(response.context['is_walkover'])

    def test_confirm_sets_status_walkover(self):
        self.client.login(username='p2', password='pass')
        self.client.post(self.url, {'action': 'confirm'})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_WALKOVER)

    def test_confirm_preserves_winner(self):
        self.client.login(username='p2', password='pass')
        self.client.post(self.url, {'action': 'confirm'})
        self.match.refresh_from_db()
        self.assertEqual(self.match.winner, self.p1)

    def test_confirm_sets_confirmed_by(self):
        self.client.login(username='p2', password='pass')
        self.client.post(self.url, {'action': 'confirm'})
        self.match.refresh_from_db()
        self.assertEqual(self.match.confirmed_by, self.p2)

    def test_confirm_sets_played_date(self):
        self.client.login(username='p2', password='pass')
        self.client.post(self.url, {'action': 'confirm'})
        self.match.refresh_from_db()
        self.assertEqual(self.match.played_date, datetime.date.today())

    def test_dispute_resets_to_scheduled(self):
        self.client.login(username='p2', password='pass')
        self.client.post(self.url, {'action': 'dispute'})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_SCHEDULED)

    def test_dispute_clears_winner(self):
        self.client.login(username='p2', password='pass')
        self.client.post(self.url, {'action': 'dispute'})
        self.match.refresh_from_db()
        self.assertIsNone(self.match.winner)

    def test_dispute_clears_walkover_reason(self):
        self.client.login(username='p2', password='pass')
        self.client.post(self.url, {'action': 'dispute'})
        self.match.refresh_from_db()
        self.assertEqual(self.match.walkover_reason, '')

    def test_dispute_clears_entered_by(self):
        self.client.login(username='p2', password='pass')
        self.client.post(self.url, {'action': 'dispute'})
        self.match.refresh_from_db()
        self.assertIsNone(self.match.entered_by)

    def test_entered_by_player_cannot_confirm_own_walkover(self):
        self.client.login(username='p1', password='pass')
        response = self.client.post(self.url, {'action': 'confirm'})
        self.assertEqual(response.status_code, 403)

    def test_staff_can_confirm_walkover(self):
        staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        self.client.login(username='staff', password='pass')
        self.client.post(self.url, {'action': 'confirm'})
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, Match.STATUS_WALKOVER)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10 — Grace period (EnterResultView) tests
# ─────────────────────────────────────────────────────────────────────────────

class GracePeriodTest(TestCase):
    def setUp(self):
        self.season = Season.objects.create(
            name='Spring', year=2025, sets_to_win=2,
            final_set_format=Season.FINAL_SET_FULL,
            grace_period_days=7,
        )
        self.p1 = User.objects.create_user(username='p1', password='pass')
        self.p2 = User.objects.create_user(username='p2', password='pass')
        self.client.login(username='p1', password='pass')

    def _match(self, scheduled_date):
        return Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            status=Match.STATUS_SCHEDULED, scheduled_date=scheduled_date,
        )

    def _get_url(self, match):
        return reverse('matches:enter_result', kwargs={'pk': match.pk})

    def test_within_grace_period_allowed(self):
        match = self._match(datetime.date.today() - datetime.timedelta(days=3))
        response = self.client.get(self._get_url(match))
        self.assertEqual(response.status_code, 200)

    def test_on_deadline_day_allowed(self):
        match = self._match(datetime.date.today() - datetime.timedelta(days=7))
        response = self.client.get(self._get_url(match))
        self.assertEqual(response.status_code, 200)

    def test_one_day_past_deadline_blocked(self):
        match = self._match(datetime.date.today() - datetime.timedelta(days=8))
        response = self.client.get(self._get_url(match))
        self.assertEqual(response.status_code, 302)

    def test_no_scheduled_date_always_allowed(self):
        match = Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            status=Match.STATUS_SCHEDULED, scheduled_date=None,
        )
        response = self.client.get(self._get_url(match))
        self.assertEqual(response.status_code, 200)

    def test_grace_period_zero_means_must_play_on_day(self):
        self.season.grace_period_days = 0
        self.season.save()
        match = self._match(datetime.date.today() - datetime.timedelta(days=1))
        response = self.client.get(self._get_url(match))
        self.assertEqual(response.status_code, 302)

    def test_large_grace_period_allows_old_match(self):
        self.season.grace_period_days = 365
        self.season.save()
        match = self._match(datetime.date.today() - datetime.timedelta(days=100))
        response = self.client.get(self._get_url(match))
        self.assertEqual(response.status_code, 200)

    def test_future_scheduled_date_always_allowed(self):
        match = self._match(datetime.date.today() + datetime.timedelta(days=5))
        response = self.client.get(self._get_url(match))
        self.assertEqual(response.status_code, 200)


# ─── Scheduler tests ──────────────────────────────────────────────────────────


class RoundRobinRoundsTest(TestCase):
    def _all_pairs(self, rounds):
        return [frozenset(pair) for round_ in rounds for pair in round_]

    def test_empty_list_returns_no_rounds(self):
        self.assertEqual(_round_robin_rounds([]), [])

    def test_single_player_returns_no_rounds(self):
        self.assertEqual(_round_robin_rounds([1]), [])

    def test_two_players_one_round_one_pair(self):
        rounds = _round_robin_rounds([1, 2])
        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0], [(1, 2)])

    def test_four_players_three_rounds(self):
        rounds = _round_robin_rounds([1, 2, 3, 4])
        self.assertEqual(len(rounds), 3)

    def test_four_players_two_pairs_per_round(self):
        for round_ in _round_robin_rounds([1, 2, 3, 4]):
            self.assertEqual(len(round_), 2)

    def test_three_players_three_rounds(self):
        # 3 players + bye → 4 slots → 3 rounds; bye player omitted each round
        rounds = _round_robin_rounds([1, 2, 3])
        self.assertEqual(len(rounds), 3)

    def test_three_players_one_pair_per_round(self):
        for round_ in _round_robin_rounds([1, 2, 3]):
            self.assertEqual(len(round_), 1)

    def test_no_player_appears_twice_in_a_round(self):
        for round_ in _round_robin_rounds([1, 2, 3, 4]):
            players_in_round = [p for pair in round_ for p in pair]
            self.assertEqual(len(players_in_round), len(set(players_in_round)))

    def test_all_pairs_unique_four_players(self):
        pairs = self._all_pairs(_round_robin_rounds([1, 2, 3, 4]))
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_all_pairs_unique_five_players(self):
        pairs = self._all_pairs(_round_robin_rounds([1, 2, 3, 4, 5]))
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_covers_all_unique_pairs_four_players(self):
        pairs = set(self._all_pairs(_round_robin_rounds([1, 2, 3, 4])))
        expected = {frozenset(p) for p in [(1,2),(1,3),(1,4),(2,3),(2,4),(3,4)]}
        self.assertEqual(pairs, expected)

    def test_covers_all_unique_pairs_three_players(self):
        pairs = set(self._all_pairs(_round_robin_rounds([1, 2, 3])))
        expected = {frozenset([1,2]), frozenset([1,3]), frozenset([2,3])}
        self.assertEqual(pairs, expected)

    def test_no_self_pairs(self):
        for pair in self._all_pairs(_round_robin_rounds([1, 2, 3, 4])):
            p1, p2 = pair
            self.assertNotEqual(p1, p2)

    def test_no_self_pairs_six_players(self):
        for pair in self._all_pairs(_round_robin_rounds([1, 2, 3, 4, 5, 6])):
            p1, p2 = pair
            self.assertNotEqual(p1, p2)


class GenerateScheduleTest(TestCase):
    START = datetime.date(2025, 3, 1)

    def _season(self, schedule_type=Season.SCHEDULE_WEEKLY, num_tiers=1):
        season = Season.objects.create(
            name='Spring', year=2025,
            schedule_type=schedule_type,
        )
        for n in range(1, num_tiers + 1):
            Tier.objects.create(season=season, number=n, name=f'Tier {n}')
        return season

    def _add_players(self, season, count, tier=1):
        players = []
        for i in range(count):
            user = User.objects.create_user(username=f'tier{tier}_p{i}')
            SeasonPlayer.objects.create(season=season, player=user, tier=tier)
            players.append(user)
        return players

    def test_returns_match_objects(self):
        season = self._season()
        self._add_players(season, 4)
        result = generate_schedule(season, self.START, 3)
        self.assertTrue(all(isinstance(m, Match) for m in result))

    def test_match_count_even_players_full_rounds(self):
        # 4 players, 3 rounds → 2 pairs/round × 3 = 6
        season = self._season()
        self._add_players(season, 4)
        self.assertEqual(len(generate_schedule(season, self.START, 3)), 6)

    def test_match_count_odd_players(self):
        # 3 players, 3 rounds → 1 pair/round × 3 = 3
        season = self._season()
        self._add_players(season, 3)
        self.assertEqual(len(generate_schedule(season, self.START, 3)), 3)

    def test_matches_persisted_to_database(self):
        season = self._season()
        self._add_players(season, 4)
        generate_schedule(season, self.START, 3)
        self.assertEqual(Match.objects.filter(season=season).count(), 6)

    def test_weekly_date_progression(self):
        season = self._season(schedule_type=Season.SCHEDULE_WEEKLY)
        self._add_players(season, 4)
        matches = generate_schedule(season, self.START, 3)
        dates = sorted(set(m.scheduled_date for m in matches))
        self.assertEqual(dates[0], self.START)
        self.assertEqual(dates[1], self.START + datetime.timedelta(weeks=1))
        self.assertEqual(dates[2], self.START + datetime.timedelta(weeks=2))

    def test_consecutive_days_date_progression(self):
        season = self._season(schedule_type=Season.SCHEDULE_CONSECUTIVE_DAYS)
        self._add_players(season, 4)
        matches = generate_schedule(season, self.START, 3)
        dates = sorted(set(m.scheduled_date for m in matches))
        self.assertEqual(dates[0], self.START)
        self.assertEqual(dates[1], self.START + datetime.timedelta(days=1))
        self.assertEqual(dates[2], self.START + datetime.timedelta(days=2))

    def test_single_day_all_matches_on_start_date(self):
        season = self._season(schedule_type=Season.SCHEDULE_SINGLE_DAY)
        self._add_players(season, 4)
        for match in generate_schedule(season, self.START, 3):
            self.assertEqual(match.scheduled_date, self.START)

    def test_num_rounds_capped_at_available(self):
        # 4 players → max 3 unique rounds; requesting 99 still produces only 6 matches
        season = self._season()
        self._add_players(season, 4)
        self.assertEqual(len(generate_schedule(season, self.START, 99)), 6)

    def test_zero_rounds_produces_no_matches(self):
        season = self._season()
        self._add_players(season, 4)
        self.assertEqual(len(generate_schedule(season, self.START, 0)), 0)

    def test_single_player_tier_produces_no_matches(self):
        season = self._season()
        self._add_players(season, 1)
        self.assertEqual(len(generate_schedule(season, self.START, 5)), 0)

    def test_empty_tier_produces_no_matches(self):
        season = self._season()
        self.assertEqual(len(generate_schedule(season, self.START, 5)), 0)

    def test_all_matches_have_scheduled_status(self):
        season = self._season()
        self._add_players(season, 4)
        for match in generate_schedule(season, self.START, 2):
            self.assertEqual(match.status, Match.STATUS_SCHEDULED)

    def test_all_matches_have_regular_round(self):
        season = self._season()
        self._add_players(season, 4)
        for match in generate_schedule(season, self.START, 2):
            self.assertEqual(match.round, Match.ROUND_REGULAR)

    def test_all_matches_reference_correct_season(self):
        season = self._season()
        self._add_players(season, 4)
        for match in generate_schedule(season, self.START, 2):
            self.assertEqual(match.season_id, season.pk)

    def test_tier_set_on_matches(self):
        season = self._season()
        self._add_players(season, 4, tier=1)
        for match in generate_schedule(season, self.START, 2):
            self.assertEqual(match.tier, 1)

    def test_no_duplicate_pairings(self):
        season = self._season()
        self._add_players(season, 4)
        matches = generate_schedule(season, self.START, 99)
        pairs = [frozenset([m.player1_id, m.player2_id]) for m in matches]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_players_only_matched_within_tier(self):
        season = self._season(num_tiers=2)
        tier1_ids = {p.pk for p in self._add_players(season, 3, tier=1)}
        tier2_ids = {p.pk for p in self._add_players(season, 3, tier=2)}
        for match in generate_schedule(season, self.START, 10):
            both_tier1 = match.player1_id in tier1_ids and match.player2_id in tier1_ids
            both_tier2 = match.player1_id in tier2_ids and match.player2_id in tier2_ids
            self.assertTrue(both_tier1 or both_tier2, msg='Cross-tier match detected')

    def test_multi_tier_produces_matches_in_each_tier(self):
        season = self._season(num_tiers=2)
        self._add_players(season, 4, tier=1)
        self._add_players(season, 4, tier=2)
        matches = generate_schedule(season, self.START, 1)
        self.assertEqual(sum(1 for m in matches if m.tier == 1), 2)
        self.assertEqual(sum(1 for m in matches if m.tier == 2), 2)

    def test_double_call_raises(self):
        season = self._season()
        self._add_players(season, 4)
        generate_schedule(season, self.START, 3)
        with self.assertRaises(ValueError):
            generate_schedule(season, self.START, 3)

    def test_inactive_players_excluded(self):
        season = self._season()
        active1 = User.objects.create_user(username='active1')
        active2 = User.objects.create_user(username='active2')
        inactive = User.objects.create_user(username='inactive')
        SeasonPlayer.objects.create(season=season, player=active1, tier=1, is_active=True)
        SeasonPlayer.objects.create(season=season, player=active2, tier=1, is_active=True)
        SeasonPlayer.objects.create(season=season, player=inactive, tier=1, is_active=False)
        matches = generate_schedule(season, self.START, 5)
        involved = {m.player1_id for m in matches} | {m.player2_id for m in matches}
        self.assertNotIn(inactive.pk, involved)


class MatchAuditLogTest(TestCase):
    """Views that mutate a match should write a LogEntry to the admin audit log."""

    def setUp(self):
        self.season = Season.objects.create(
            name='Spring 2025', year=2025,
            sets_to_win=1,
        )
        self.p1 = User.objects.create_user(username='alice', first_name='Alice', last_name='Smith')
        self.p2 = User.objects.create_user(username='bob', first_name='Bob', last_name='Jones')
        SeasonPlayer.objects.create(season=self.season, player=self.p1, tier=1)
        SeasonPlayer.objects.create(season=self.season, player=self.p2, tier=1)

    def _match(self, **kwargs):
        return Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2, tier=1, **kwargs
        )

    def _entries(self, match):
        ct = ContentType.objects.get_for_model(Match)
        return list(LogEntry.objects.filter(content_type=ct, object_id=match.pk))

    def test_enter_result_logs_set_scores(self):
        match = self._match(status=Match.STATUS_SCHEDULED)
        self.client.force_login(self.p1)
        self.client.post(
            reverse('matches:enter_result', args=[match.pk]),
            {'set1_p1': '6', 'set1_p2': '3', 'set1_tb_p1': '', 'set1_tb_p2': ''},
        )
        entries = self._entries(match)
        self.assertEqual(len(entries), 1)
        self.assertIn('Result submitted', entries[0].change_message)
        self.assertIn('6', entries[0].change_message)
        self.assertIn('3', entries[0].change_message)
        self.assertEqual(entries[0].user_id, self.p1.pk)

    def test_enter_result_no_log_on_invalid_form(self):
        match = self._match(status=Match.STATUS_SCHEDULED)
        self.client.force_login(self.p1)
        self.client.post(
            reverse('matches:enter_result', args=[match.pk]),
            {'set1_p1': '', 'set1_p2': '', 'set1_tb_p1': '', 'set1_tb_p2': ''},
        )
        self.assertEqual(len(self._entries(match)), 0)

    def test_admin_enter_result_logs_submission_and_auto_confirm(self):
        staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        match = self._match(status=Match.STATUS_SCHEDULED)
        self.client.force_login(staff)
        self.client.post(
            reverse('matches:enter_result', args=[match.pk]),
            {'set1_p1': '6', 'set1_p2': '3', 'set1_tb_p1': '', 'set1_tb_p2': ''},
        )
        entries = self._entries(match)
        self.assertEqual(len(entries), 2)
        messages = [e.change_message for e in entries]
        self.assertTrue(any('Result submitted' in m for m in messages))
        self.assertTrue(any('auto-confirmed' in m for m in messages))

    def test_admin_walkover_logs_submission_and_auto_confirm(self):
        staff = User.objects.create_user(username='staff', password='pass', is_staff=True)
        match = self._match(status=Match.STATUS_SCHEDULED)
        self.client.force_login(staff)
        self.client.post(
            reverse('matches:walkover', args=[match.pk]),
            {'winner': 'player1', 'reason': ''},
        )
        entries = self._entries(match)
        self.assertEqual(len(entries), 2)
        messages = [e.change_message for e in entries]
        self.assertTrue(any('Walkover submitted' in m for m in messages))
        self.assertTrue(any('auto-confirmed' in m for m in messages))

    def test_confirm_result_logs_winner(self):
        match = self._match(status=Match.STATUS_PENDING, entered_by=self.p1)
        MatchSet.objects.create(match=match, set_number=1, player1_games=6, player2_games=3)
        self.client.force_login(self.p2)
        self.client.post(reverse('matches:confirm_result', args=[match.pk]), {'action': 'confirm'})
        entries = self._entries(match)
        self.assertEqual(len(entries), 1)
        self.assertIn('Result confirmed', entries[0].change_message)
        self.assertIn('Alice Smith', entries[0].change_message)
        self.assertEqual(entries[0].user_id, self.p2.pk)

    def test_confirm_walkover_logs_correctly(self):
        match = self._match(status=Match.STATUS_PENDING, entered_by=self.p1, winner=self.p1)
        self.client.force_login(self.p2)
        self.client.post(reverse('matches:confirm_result', args=[match.pk]), {'action': 'confirm'})
        entries = self._entries(match)
        self.assertEqual(len(entries), 1)
        self.assertIn('Walkover confirmed', entries[0].change_message)

    def test_dispute_result_logs_dispute(self):
        match = self._match(status=Match.STATUS_PENDING, entered_by=self.p1)
        MatchSet.objects.create(match=match, set_number=1, player1_games=6, player2_games=3)
        self.client.force_login(self.p2)
        self.client.post(reverse('matches:confirm_result', args=[match.pk]), {'action': 'dispute'})
        entries = self._entries(match)
        self.assertEqual(len(entries), 1)
        self.assertIn('disputed', entries[0].change_message)
        self.assertEqual(entries[0].user_id, self.p2.pk)

    def test_walkover_submission_logs_winner_and_reason(self):
        match = self._match(status=Match.STATUS_SCHEDULED)
        self.client.force_login(self.p1)
        self.client.post(
            reverse('matches:walkover', args=[match.pk]),
            {'winner': 'player1', 'reason': 'Injury'},
        )
        entries = self._entries(match)
        self.assertEqual(len(entries), 1)
        self.assertIn('Walkover submitted', entries[0].change_message)
        self.assertIn('Alice Smith', entries[0].change_message)
        self.assertIn('Injury', entries[0].change_message)
        self.assertEqual(entries[0].user_id, self.p1.pk)

    def test_walkover_no_reason_omits_reason_from_log(self):
        match = self._match(status=Match.STATUS_SCHEDULED)
        self.client.force_login(self.p1)
        self.client.post(
            reverse('matches:walkover', args=[match.pk]),
            {'winner': 'player2', 'reason': ''},
        )
        entries = self._entries(match)
        self.assertEqual(len(entries), 1)
        self.assertNotIn('Reason', entries[0].change_message)

    def test_postpone_logs_new_date_and_reason(self):
        match = self._match(status=Match.STATUS_SCHEDULED)
        self.client.force_login(self.p1)
        new_date = datetime.date.today() + datetime.timedelta(days=7)
        self.client.post(
            reverse('matches:postpone', args=[match.pk]),
            {'new_date': new_date.isoformat(), 'reason': 'Travel'},
        )
        entries = self._entries(match)
        self.assertEqual(len(entries), 1)
        self.assertIn('postponed', entries[0].change_message)
        self.assertIn(str(new_date), entries[0].change_message)
        self.assertIn('Travel', entries[0].change_message)
        self.assertEqual(entries[0].user_id, self.p1.pk)

    def test_postpone_no_reason_omits_reason_from_log(self):
        match = self._match(status=Match.STATUS_SCHEDULED)
        self.client.force_login(self.p1)
        new_date = datetime.date.today() + datetime.timedelta(days=7)
        self.client.post(
            reverse('matches:postpone', args=[match.pk]),
            {'new_date': new_date.isoformat(), 'reason': ''},
        )
        entries = self._entries(match)
        self.assertEqual(len(entries), 1)
        self.assertNotIn('Reason', entries[0].change_message)
