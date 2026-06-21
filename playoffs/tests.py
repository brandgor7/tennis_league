from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from leagues.models import Season, SeasonPlayer, Tier
from matches.models import Match, PLAYOFF_ROUND_CHOICES
from .models import PlayoffBracket, PlayoffSlot
from .generator import bracket_size_for, generate_bracket

User = get_user_model()


def _make_season(**kwargs):
    defaults = dict(
        name='Spring', year=2025,
        sets_to_win=2, final_set_format='tiebreak',
        playoff_qualifiers_count=8,
        points_for_win=3, points_for_loss=0, points_for_walkover_loss=0,
    )
    defaults.update(kwargs)
    return Season.objects.create(**defaults)


def _make_players(n):
    return [User.objects.create_user(username=f'p{i}') for i in range(1, n + 1)]


def _enroll(season, players, tier=1):
    for p in players:
        SeasonPlayer.objects.create(season=season, player=p, tier=tier)


def _complete_match(season, p1, p2, tier=1):
    """Create a completed match where p1 wins 2-0."""
    m = Match.objects.create(
        season=season, player1=p1, player2=p2, tier=tier,
        status=Match.STATUS_COMPLETED, winner=p1,
    )
    from matches.models import MatchSet
    MatchSet.objects.create(match=m, set_number=1, player1_games=6, player2_games=3)
    MatchSet.objects.create(match=m, set_number=2, player1_games=6, player2_games=2)
    return m


class BracketSizeForTest(TestCase):
    def test_exact_powers_of_two_unchanged(self):
        self.assertEqual(bracket_size_for(2), 2)
        self.assertEqual(bracket_size_for(4), 4)
        self.assertEqual(bracket_size_for(8), 8)
        self.assertEqual(bracket_size_for(16), 16)
        self.assertEqual(bracket_size_for(32), 32)

    def test_rounds_up_to_next_power_of_two(self):
        self.assertEqual(bracket_size_for(3), 4)
        self.assertEqual(bracket_size_for(5), 8)
        self.assertEqual(bracket_size_for(6), 8)
        self.assertEqual(bracket_size_for(7), 8)
        self.assertEqual(bracket_size_for(9), 16)
        self.assertEqual(bracket_size_for(20), 32)

    def test_fewer_than_two_returns_zero(self):
        self.assertEqual(bracket_size_for(0), 0)
        self.assertEqual(bracket_size_for(1), 0)


class PlayoffBracketModelTest(TestCase):
    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)
        self.admin = User.objects.create_user(username='admin')

    def test_str_includes_tier(self):
        bracket = PlayoffBracket(season=self.season, tier=1)
        self.assertEqual(str(bracket), 'Playoff Bracket — Spring 2025 (Tier 1)')

    def test_str_tier_2(self):
        bracket = PlayoffBracket(season=self.season, tier=2)
        self.assertEqual(str(bracket), 'Playoff Bracket — Spring 2025 (Tier 2)')

    def test_unique_together_enforced(self):
        PlayoffBracket.objects.create(season=self.season, tier=1)
        with self.assertRaises(IntegrityError):
            PlayoffBracket.objects.create(season=self.season, tier=1)

    def test_different_tiers_allowed_same_season(self):
        PlayoffBracket.objects.create(season=self.season, tier=1)
        PlayoffBracket.objects.create(season=self.season, tier=2)
        self.assertEqual(PlayoffBracket.objects.filter(season=self.season).count(), 2)

    def test_season_is_fk_not_unique(self):
        season2 = Season.objects.create(name='Fall', year=2025)
        PlayoffBracket.objects.create(season=self.season, tier=1)
        PlayoffBracket.objects.create(season=season2, tier=1)
        self.assertEqual(PlayoffBracket.objects.count(), 2)

    def test_default_tier_is_1(self):
        bracket = PlayoffBracket.objects.create(season=self.season)
        self.assertEqual(bracket.tier, 1)

    def test_str_uses_named_tier_when_configured(self):
        Tier.objects.create(season=self.season, number=1, name='Premier')
        bracket = PlayoffBracket.objects.create(season=self.season, tier=1)
        self.assertEqual(str(bracket), 'Playoff Bracket — Spring 2025 (Premier)')


class PlayoffSlotModelTest(TestCase):
    def test_round_field_uses_shared_choices(self):
        field = PlayoffSlot._meta.get_field('round')
        self.assertEqual(field.choices, PLAYOFF_ROUND_CHOICES)


class GenerateBracketTest(TestCase):
    def setUp(self):
        self.season = _make_season(playoff_qualifiers_count=8)
        self.admin = User.objects.create_user(username='admin')
        self.players = _make_players(8)
        _enroll(self.season, self.players)
        # Give each player a win so they appear in standings
        for i in range(0, 8, 2):
            _complete_match(self.season, self.players[i], self.players[i - 1])

    def test_creates_bracket(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        self.assertIsInstance(bracket, PlayoffBracket)
        self.assertEqual(bracket.season, self.season)
        self.assertEqual(bracket.tier, 1)

    def test_correct_number_of_slots(self):
        # 8-player bracket: QF (4) + SF (2) + F (1) = 7 slots
        bracket = generate_bracket(self.season, 1, self.admin)
        self.assertEqual(bracket.slots.count(), 7)

    def test_correct_number_of_matches(self):
        generate_bracket(self.season, 1, self.admin)
        self.assertEqual(Match.objects.filter(season=self.season, round=Match.ROUND_QF).count(), 4)
        self.assertEqual(Match.objects.filter(season=self.season, round=Match.ROUND_SF).count(), 2)
        self.assertEqual(Match.objects.filter(season=self.season, round=Match.ROUND_FINAL).count(), 1)

    def test_first_round_matches_have_players(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        qf_slots = bracket.slots.filter(round=Match.ROUND_QF)
        for slot in qf_slots:
            self.assertIsNotNone(slot.match.player1)
            self.assertIsNotNone(slot.match.player2)

    def test_later_round_matches_have_no_players(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        sf_slots = bracket.slots.filter(round=Match.ROUND_SF)
        for slot in sf_slots:
            self.assertIsNone(slot.match.player1)
            self.assertIsNone(slot.match.player2)

    def test_next_slot_links_are_set(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        qf_slots = bracket.slots.filter(round=Match.ROUND_QF).order_by('bracket_position')
        for slot in qf_slots:
            self.assertIsNotNone(slot.next_slot)
            self.assertEqual(slot.next_slot.round, Match.ROUND_SF)

    def test_duplicate_bracket_raises(self):
        generate_bracket(self.season, 1, self.admin)
        with self.assertRaises(ValueError):
            generate_bracket(self.season, 1, self.admin)

    def test_insufficient_players_raises(self):
        season2 = _make_season(name='Fall', year=2025, playoff_qualifiers_count=8)
        solo = User.objects.create_user(username='solo_player')
        _enroll(season2, [solo])
        with self.assertRaises(ValueError):
            generate_bracket(season2, 1, self.admin)

    def test_sixteen_player_bracket(self):
        season2 = _make_season(name='Winter', year=2025, playoff_qualifiers_count=16)
        players = [User.objects.create_user(username=f'w{i}') for i in range(1, 17)]
        _enroll(season2, players)
        for i in range(0, 16, 2):
            _complete_match(season2, players[i], players[i - 1])
        bracket = generate_bracket(season2, 1, self.admin)
        # 16-player bracket: R16 (8) + QF (4) + SF (2) + F (1) = 15 slots
        self.assertEqual(bracket.slots.count(), 15)
        self.assertEqual(bracket.slots.filter(round=Match.ROUND_R16).count(), 8)


class WinnerAdvancementTest(TestCase):
    def setUp(self):
        # 4-player bracket → first round is SF (2 matches), second round is Final (1 match)
        self.season = _make_season(playoff_qualifiers_count=4)
        self.admin = User.objects.create_user(username='adv_admin')
        self.players = [User.objects.create_user(username=f'adv{i}') for i in range(1, 5)]
        _enroll(self.season, self.players)
        for i in range(0, 4, 2):
            _complete_match(self.season, self.players[i], self.players[i - 1])

    def test_winner_advances_to_next_round(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        final_slot = bracket.slots.filter(round=Match.ROUND_FINAL).first()
        final_match = final_slot.match

        # Complete the first SF match
        sf_slot = bracket.slots.filter(round=Match.ROUND_SF).order_by('bracket_position').first()
        sf_match = sf_slot.match
        sf_match.status = Match.STATUS_COMPLETED
        sf_match.winner = sf_match.player1
        sf_match.save()

        final_match.refresh_from_db()
        self.assertEqual(final_match.player1, sf_match.player1)

    def test_second_winner_becomes_player2(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        final_slot = bracket.slots.filter(round=Match.ROUND_FINAL).first()
        final_match = final_slot.match

        sf_slots = final_slot.previous_slots.order_by('bracket_position')
        first_sf = sf_slots[0].match
        second_sf = sf_slots[1].match

        first_sf.status = Match.STATUS_COMPLETED
        first_sf.winner = first_sf.player1
        first_sf.save()

        second_sf.status = Match.STATUS_COMPLETED
        second_sf.winner = second_sf.player2
        second_sf.save()

        final_match.refresh_from_db()
        self.assertEqual(final_match.player1, first_sf.player1)
        self.assertEqual(final_match.player2, second_sf.player2)


class GenerateBracketWithByesTest(TestCase):
    """6 qualifiers → 8-bracket (ceiling) → 2 byes for top seeds."""

    def setUp(self):
        # _seed_order(8) = [1, 8, 4, 5, 2, 7, 3, 6]
        # Seeds 7 and 8 don't exist, so QF matches (seed1 v seed8) and
        # (seed2 v seed7) become byes; (seed4 v seed5) and (seed3 v seed6) are real.
        self.season = _make_season(playoff_qualifiers_count=6)
        self.admin = User.objects.create_user(username='bye_admin')
        self.players = _make_players(6)
        _enroll(self.season, self.players)
        for i in range(0, 6, 2):
            _complete_match(self.season, self.players[i], self.players[i - 1])

    def test_bracket_uses_eight_slot_structure(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        # 8-bracket: QF(4) + SF(2) + F(1) = 7 slots
        self.assertEqual(bracket.slots.count(), 7)
        self.assertEqual(bracket.slots.filter(round=Match.ROUND_QF).count(), 4)

    def test_two_bye_matches_created(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        qf_slots = bracket.slots.filter(round=Match.ROUND_QF)
        bye_matches = [
            s.match for s in qf_slots
            if (s.match.player1 is None) != (s.match.player2 is None)
        ]
        self.assertEqual(len(bye_matches), 2)

    def test_two_real_matches_created(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        qf_slots = bracket.slots.filter(round=Match.ROUND_QF)
        real_matches = [
            s.match for s in qf_slots
            if s.match.player1 is not None and s.match.player2 is not None
        ]
        self.assertEqual(len(real_matches), 2)
        for m in real_matches:
            self.assertEqual(m.status, Match.STATUS_SCHEDULED)

    def test_bye_matches_are_walkovers_with_winner(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        qf_slots = bracket.slots.filter(round=Match.ROUND_QF)
        for slot in qf_slots:
            m = slot.match
            is_bye = (m.player1 is None) != (m.player2 is None)
            if is_bye:
                self.assertEqual(m.status, Match.STATUS_WALKOVER)
                self.assertIsNotNone(m.winner)
                self.assertIn(m.winner, [m.player1, m.player2])

    def test_bye_winners_advanced_into_sf(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        qf_slots = bracket.slots.filter(round=Match.ROUND_QF).order_by('bracket_position')
        for slot in qf_slots:
            m = slot.match
            if (m.player1 is None) != (m.player2 is None):
                next_match = slot.next_slot.match
                self.assertIn(m.winner, [next_match.player1, next_match.player2])

    def test_sf_has_two_players_from_byes(self):
        bracket = generate_bracket(self.season, 1, self.admin)
        sf_matches = [s.match for s in bracket.slots.filter(round=Match.ROUND_SF)]
        players_filled = sum(
            1 for m in sf_matches
            for p in [m.player1, m.player2] if p is not None
        )
        self.assertEqual(players_filled, 2)


class CenteredBracketStyleTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', is_staff=True)
        self.season = _make_season(
            playoff_qualifiers_count=8,
            playoff_bracket_style=Season.BRACKET_STYLE_CENTERED,
        )
        self.players = _make_players(8)
        _enroll(self.season, self.players)
        # Give every player a completed match so standings are populated.
        for i in range(0, 8, 2):
            _complete_match(self.season, self.players[i], self.players[i + 1])
        generate_bracket(self.season, 1, self.admin)

    def _url(self):
        from django.urls import reverse
        return reverse('leagues:playoffs', args=[self.season.slug])

    def test_centered_page_renders(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'class="cb-node')
        self.assertNotContains(resp, 'class="bracket-match')

    def test_generated_bracket_not_shown_as_preview_without_tier(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['tiers_data'][0]['is_preview'])
        self.assertNotContains(resp, 'badge bg-secondary">Preview')

    def test_completed_match_winner_advances_only_one_round(self):
        from .views import _bracket_context, _centered_layout
        bracket = PlayoffBracket.objects.get(season=self.season, tier=1)
        qf_match = bracket.slots.filter(
            round=Match.ROUND_QF
        ).order_by('bracket_position').first().match
        qf_match.status = Match.STATUS_COMPLETED
        qf_match.winner = qf_match.player1
        qf_match.save()
        winner = qf_match.player1

        rounds_data, bracket_size = _bracket_context(bracket)
        layout = _centered_layout(rounds_data, bracket_size)
        winner_nodes = [
            n for n in layout['nodes']
            if n['kind'] in ('winner', 'champion') and n['player'] == winner
        ]
        self.assertEqual(len(winner_nodes), 1)

    def test_traditional_page_still_renders(self):
        self.season.playoff_bracket_style = Season.BRACKET_STYLE_TRADITIONAL
        self.season.save(update_fields=['playoff_bracket_style'])
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'class="bracket-match')
        self.assertNotContains(resp, 'class="cb-node')

    def test_centered_preview_renders_without_bracket(self):
        season = _make_season(
            name='Autumn', year=2025,
            playoff_qualifiers_count=4,
            playoff_bracket_style=Season.BRACKET_STYLE_CENTERED,
        )
        players = [User.objects.create_user(username=f'q{i}') for i in range(4)]
        _enroll(season, players)
        _complete_match(season, players[0], players[1])
        _complete_match(season, players[2], players[3])
        from django.urls import reverse
        resp = self.client.get(reverse('leagues:playoffs', args=[season.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'class="cb-node')
