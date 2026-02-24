from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from leagues.models import Season
from .models import Match, MatchSet

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
