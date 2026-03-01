from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from leagues.models import Season
from matches.models import PLAYOFF_ROUND_CHOICES
from .models import PlayoffBracket, PlayoffSlot

User = get_user_model()


class PlayoffBracketTest(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.admin = User.objects.create_user(username='admin')

    def test_str_includes_tier(self):
        bracket = PlayoffBracket(season=self.season, tier=1)
        self.assertEqual(str(bracket), 'Playoff Bracket — Spring (2025) (Tier 1)')

    def test_str_tier_2(self):
        bracket = PlayoffBracket(season=self.season, tier=2)
        self.assertEqual(str(bracket), 'Playoff Bracket — Spring (2025) (Tier 2)')

    def test_unique_together_enforced(self):
        PlayoffBracket.objects.create(season=self.season, tier=1)
        with self.assertRaises(IntegrityError):
            PlayoffBracket.objects.create(season=self.season, tier=1)

    def test_different_tiers_allowed_same_season(self):
        PlayoffBracket.objects.create(season=self.season, tier=1)
        # Should not raise
        PlayoffBracket.objects.create(season=self.season, tier=2)
        self.assertEqual(PlayoffBracket.objects.filter(season=self.season).count(), 2)

    def test_season_is_fk_not_unique(self):
        """season field is now a ForeignKey, not OneToOneField — multiple brackets per season allowed."""
        season2 = Season.objects.create(name='Fall', year=2025)
        PlayoffBracket.objects.create(season=self.season, tier=1)
        PlayoffBracket.objects.create(season=season2, tier=1)
        self.assertEqual(PlayoffBracket.objects.count(), 2)

    def test_default_tier_is_1(self):
        bracket = PlayoffBracket.objects.create(season=self.season)
        self.assertEqual(bracket.tier, 1)


class PlayoffSlotTest(TestCase):
    def test_round_field_uses_shared_choices(self):
        field = PlayoffSlot._meta.get_field('round')
        self.assertEqual(field.choices, PLAYOFF_ROUND_CHOICES)
