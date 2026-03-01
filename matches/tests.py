from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from leagues.models import Season, SeasonPlayer
from .models import Match, MatchSet
from .forms import MatchScheduleForm

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
        self.season = Season.objects.create(name='Spring', year=2025, num_tiers=2)
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

    def test_cross_tier_error_message(self):
        # Use no tier kwarg so the dropdown isn't pre-filtered — then clean()
        # still enforces the cross-tier rule.
        data = {'player1': self.p1.pk, 'player2': self.p3.pk, 'tier': 1}
        form = MatchScheduleForm(data=data, season=self.season)
        form.is_valid()
        self.assertIn('same tier', str(form.errors))

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
