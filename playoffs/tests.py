from django.test import TestCase
from django.contrib.auth import get_user_model

from leagues.models import Season
from matches.models import PLAYOFF_ROUND_CHOICES
from .models import PlayoffBracket, PlayoffSlot

User = get_user_model()


class PlayoffBracketTest(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.admin = User.objects.create_user(username='admin')

    def test_str(self):
        bracket = PlayoffBracket(season=self.season)
        self.assertEqual(str(bracket), 'Playoff Bracket — Spring (2025)')


class PlayoffSlotTest(TestCase):
    def test_round_field_uses_shared_choices(self):
        field = PlayoffSlot._meta.get_field('round')
        self.assertEqual(field.choices, PLAYOFF_ROUND_CHOICES)
