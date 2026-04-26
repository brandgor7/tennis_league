import datetime

from django.test import TestCase, SimpleTestCase
from django.contrib.auth import get_user_model

from leagues.models import Season, SeasonPlayer
from matches.models import Match
from matches.bulk_result_parser import (
    parse_whatsapp_messages,
    _parse_line,
    resolve_results,
    name_score,
)

User = get_user_model()

WHATSAPP_SAMPLE = """\
[4/22, 10:38 PM] +1 (555) 000-0001: Moshe Roth over me 8:4
[4/23, 6:55 PM] +1 (555) 000-0002: Basch d Sternman 8-7
[4/23, 7:25 PM] +1 (555) 000-0003: Ed Wolf over Yakov Abramowitz 8-1
[4/23, 7:31 PM] Zvi Calko: Blackman d calko 8-3
[4/24, 2:56 PM] +1 (555) 000-0004: @⁨~Abie⁩ wins 8-7. Moral victory for me.
[4/24, 4:37 PM] +1 (555) 000-0005: T2 Kanter def Roth 8-4
"""


class ParseLineTest(SimpleTestCase):
    """Pure-parsing tests — no database required."""

    # ── Tests derived from whatsapp.txt ──────────────────────────────────

    def test_over_me_colon_score(self):
        """'Moshe Roth over me 8:4' → Roth wins 8-4, opponent is poster (None)."""
        r = _parse_line('[4/22, 10:38 PM] +1 (555) 000-0001: Moshe Roth over me 8:4')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Moshe Roth')
        self.assertIsNone(r.loser_raw)
        self.assertEqual(r.score1, 8)
        self.assertEqual(r.score2, 4)
        self.assertIsNone(r.poster_name)  # phone number → no name

    def test_d_verb_dash_score(self):
        """'Basch d Sternman 8-7' → Basch wins 8-7 over Sternman."""
        r = _parse_line('[4/23, 6:55 PM] +1 (555) 000-0002: Basch d Sternman 8-7')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Basch')
        self.assertEqual(r.loser_raw, 'Sternman')
        self.assertEqual(r.score1, 8)
        self.assertEqual(r.score2, 7)

    def test_over_verb_full_names(self):
        """'Ed Wolf over Yakov Abramowitz 8-1' → Wolf wins 8-1."""
        r = _parse_line('[4/23, 7:25 PM] +1 (555) 000-0003: Ed Wolf over Yakov Abramowitz 8-1')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Ed Wolf')
        self.assertEqual(r.loser_raw, 'Yakov Abramowitz')
        self.assertEqual(r.score1, 8)
        self.assertEqual(r.score2, 1)

    def test_d_verb_with_known_poster(self):
        """'Zvi Calko: Blackman d calko 8-3' → Blackman wins 8-3; poster name extracted."""
        r = _parse_line('[4/23, 7:31 PM] Zvi Calko: Blackman d calko 8-3')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Blackman')
        self.assertEqual(r.loser_raw, 'calko')
        self.assertEqual(r.score1, 8)
        self.assertEqual(r.score2, 3)
        self.assertEqual(r.poster_name, 'Zvi Calko')

    def test_wins_verb_wa_tag(self):
        """'@⁨~Abie⁩ wins 8-7' → Abie wins 8-7, opponent is poster (None)."""
        r = _parse_line(
            '[4/24, 2:56 PM] +1 (555) 000-0004: @⁨~Abie⁩ wins 8-7. Moral victory for me.'
        )
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Abie')
        self.assertIsNone(r.loser_raw)
        self.assertEqual(r.score1, 8)
        self.assertEqual(r.score2, 7)

    def test_def_verb_tier_prefix(self):
        """'T2 Kanter def Roth 8-4' → tier prefix stripped; Kanter wins 8-4."""
        r = _parse_line('[4/24, 4:37 PM] +1 (555) 000-0005: T2 Kanter def Roth 8-4')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Kanter')
        self.assertEqual(r.loser_raw, 'Roth')
        self.assertEqual(r.score1, 8)
        self.assertEqual(r.score2, 4)

    # ── Verb variants ─────────────────────────────────────────────────────

    def test_defeated_verb(self):
        """'Smith defeated Jones 6-2' → Smith wins 6-2."""
        r = _parse_line('Smith defeated Jones 6-2')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Smith')
        self.assertEqual(r.loser_raw, 'Jones')
        self.assertEqual(r.score1, 6)
        self.assertEqual(r.score2, 2)

    def test_beat_verb(self):
        """'Brown beat Green 10-8' → Brown wins 10-8."""
        r = _parse_line('Brown beat Green 10-8')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Brown')
        self.assertEqual(r.loser_raw, 'Green')
        self.assertEqual(r.score1, 10)
        self.assertEqual(r.score2, 8)

    def test_beats_verb(self):
        """'Adams beats Baker 8-5' → Adams wins 8-5."""
        r = _parse_line('Adams beats Baker 8-5')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Adams')
        self.assertEqual(r.loser_raw, 'Baker')

    def test_won_verb(self):
        """'Cohen won 8:3' → Cohen wins 8-3, opponent is poster."""
        r = _parse_line('Cohen won 8:3')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Cohen')
        self.assertIsNone(r.loser_raw)
        self.assertEqual(r.score1, 8)
        self.assertEqual(r.score2, 3)

    def test_d_dot_verb_me(self):
        """'Player d. me 8-2' → Player wins 8-2, opponent is poster."""
        r = _parse_line('Player d. me 8-2')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Player')
        self.assertIsNone(r.loser_raw)

    def test_def_dot_verb(self):
        """'White def. Black 6:4' → White wins 6-4."""
        r = _parse_line('White def. Black 6:4')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'White')
        self.assertEqual(r.loser_raw, 'Black')

    # ── Tier prefix variants ───────────────────────────────────────────────

    def test_tier_word_prefix(self):
        """'Tier 1 Adams def Baker 8-5' → tier prefix stripped."""
        r = _parse_line('Tier 1 Adams def Baker 8-5')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Adams')
        self.assertEqual(r.loser_raw, 'Baker')

    def test_tier_number_only_prefix(self):
        """'T3 Lee over Kim 8-6' → tier prefix stripped."""
        r = _parse_line('T3 Lee over Kim 8-6')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Lee')
        self.assertEqual(r.loser_raw, 'Kim')

    # ── No header ─────────────────────────────────────────────────────────

    def test_plain_text_no_header(self):
        """Plain text without WA header still parses correctly."""
        r = _parse_line('Kanter def Roth 8-4')
        self.assertIsNotNone(r)
        self.assertEqual(r.winner_raw, 'Kanter')
        self.assertEqual(r.loser_raw, 'Roth')
        self.assertIsNone(r.poster_name)

    # ── Failure cases ─────────────────────────────────────────────────────

    def test_no_score_returns_none(self):
        """Text with no score returns None."""
        self.assertIsNone(_parse_line('[4/22] Player: Great match today!'))

    def test_no_verb_returns_none(self):
        """Score present but no verb → None."""
        self.assertIsNone(_parse_line('Random text 8-4'))

    def test_empty_line_returns_none(self):
        """Empty line returns None."""
        self.assertIsNone(_parse_line(''))

    def test_whitespace_line_returns_none(self):
        """Whitespace-only line returns None."""
        self.assertIsNone(_parse_line('   '))

    # ── Bulk parse ────────────────────────────────────────────────────────

    def test_bulk_parse_all_six_messages(self):
        """All 6 messages from whatsapp.txt are successfully parsed."""
        results = parse_whatsapp_messages(WHATSAPP_SAMPLE)
        self.assertEqual(len(results), 6)

    def test_bulk_parse_preserves_order(self):
        """Parsed results are in the same order as the input lines."""
        results = parse_whatsapp_messages(WHATSAPP_SAMPLE)
        self.assertEqual(results[0].winner_raw, 'Moshe Roth')
        self.assertEqual(results[1].winner_raw, 'Basch')
        self.assertEqual(results[2].winner_raw, 'Ed Wolf')
        self.assertEqual(results[3].winner_raw, 'Blackman')
        self.assertEqual(results[4].winner_raw, 'Abie')
        self.assertEqual(results[5].winner_raw, 'Kanter')


class NameScoreTest(TestCase):
    """Tests for the name similarity scoring function."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='jsmith',
            first_name='John',
            last_name='Smith',
        )

    def test_exact_full_name(self):
        self.assertEqual(name_score('John Smith', self.user), 100)

    def test_exact_full_name_case_insensitive(self):
        self.assertEqual(name_score('john smith', self.user), 100)

    def test_exact_last_name(self):
        self.assertEqual(name_score('Smith', self.user), 80)

    def test_exact_last_name_case_insensitive(self):
        self.assertEqual(name_score('smith', self.user), 80)

    def test_exact_first_name(self):
        # Exact first-name match scores 70, ranked above substring-of-full-name (60)
        self.assertEqual(name_score('John', self.user), 70)

    def test_substring_of_full_name(self):
        # Partial match like "John Sm" scores as substring of full name (60)
        self.assertEqual(name_score('John Sm', self.user), 60)

    def test_partial_last_name(self):
        self.assertGreater(name_score('Smit', self.user), 0)

    def test_no_match(self):
        self.assertEqual(name_score('Completely Different', self.user), 0)

    def test_username_fallback(self):
        self.assertGreater(name_score('jsmith', self.user), 0)


class ResolveResultsTest(TestCase):
    """Integration tests for resolve_results — requires DB."""

    def setUp(self):
        self.season = Season.objects.create(name='Spring', year=2025)

        self.roth = User.objects.create_user(
            username='mroth', first_name='Moshe', last_name='Roth'
        )
        self.kanter = User.objects.create_user(
            username='kanter', first_name='David', last_name='Kanter'
        )
        self.blackman = User.objects.create_user(
            username='blackman', first_name='Ari', last_name='Blackman'
        )
        self.calko = User.objects.create_user(
            username='calko', first_name='Zvi', last_name='Calko'
        )
        self.wolf = User.objects.create_user(
            username='ewolf', first_name='Ed', last_name='Wolf'
        )
        self.abramowitz = User.objects.create_user(
            username='yabramowitz', first_name='Yakov', last_name='Abramowitz'
        )

        for user in [self.roth, self.kanter, self.blackman, self.calko, self.wolf, self.abramowitz]:
            SeasonPlayer.objects.create(season=self.season, player=user, tier=1)

        self.match_roth_kanter = Match.objects.create(
            season=self.season, player1=self.roth, player2=self.kanter,
            tier=1, status=Match.STATUS_SCHEDULED,
            scheduled_date=datetime.date(2025, 4, 24),
        )
        self.match_blackman_calko = Match.objects.create(
            season=self.season, player1=self.blackman, player2=self.calko,
            tier=1, status=Match.STATUS_SCHEDULED,
            scheduled_date=datetime.date(2025, 4, 23),
        )
        self.match_wolf_abramowitz = Match.objects.create(
            season=self.season, player1=self.wolf, player2=self.abramowitz,
            tier=1, status=Match.STATUS_SCHEDULED,
            scheduled_date=datetime.date(2025, 4, 23),
        )

    def _parse_and_resolve(self, text):
        parsed = parse_whatsapp_messages(text)
        return resolve_results(parsed, self.season)

    def test_resolve_def_verb(self):
        """'T2 Kanter def Roth 8-4' resolves to Kanter winning over Roth."""
        results = self._parse_and_resolve(
            '[4/24, 4:37 PM] +1 (555) 000-0005: T2 Kanter def Roth 8-4'
        )
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertIsNone(r.error)
        self.assertEqual(r.winner, self.kanter)
        self.assertEqual(r.loser, self.roth)
        self.assertEqual(r.winner_score, 8)
        self.assertEqual(r.loser_score, 4)
        self.assertIsNotNone(r.match)
        self.assertGreater(r.confidence, 50)

    def test_resolve_over_full_names(self):
        """'Ed Wolf over Yakov Abramowitz 8-1' resolves correctly."""
        results = self._parse_and_resolve(
            '[4/23, 7:25 PM] +1 (667) 439-2033: Ed Wolf over Yakov Abramowitz 8-1'
        )
        r = results[0]
        self.assertIsNone(r.error)
        self.assertEqual(r.winner, self.wolf)
        self.assertEqual(r.loser, self.abramowitz)
        self.assertEqual(r.winner_score, 8)
        self.assertEqual(r.loser_score, 1)

    def test_resolve_d_verb_with_poster_as_loser(self):
        """'Zvi Calko: Blackman d calko 8-3' — poster 'calko' resolves to Zvi Calko."""
        results = self._parse_and_resolve(
            '[4/23, 7:31 PM] Zvi Calko: Blackman d calko 8-3'
        )
        r = results[0]
        self.assertIsNone(r.error)
        self.assertEqual(r.winner, self.blackman)
        self.assertEqual(r.loser, self.calko)
        self.assertEqual(r.winner_score, 8)
        self.assertEqual(r.loser_score, 3)

    def test_resolve_me_with_unknown_poster_infers_from_match(self):
        """'Moshe Roth over me 8:4' — poster unknown; opponent inferred from scheduled match."""
        results = self._parse_and_resolve(
            '[4/22, 10:38 PM] +1 (443) 889-7070: Moshe Roth over me 8:4'
        )
        r = results[0]
        self.assertEqual(r.winner, self.roth)
        self.assertIsNotNone(r.loser)
        self.assertEqual(r.winner_score, 8)
        self.assertEqual(r.loser_score, 4)

    def test_resolve_poster_name_takes_priority_over_match_inference(self):
        """When the poster is known, they are used as the loser instead of the first scheduled match.

        Kanter has two scheduled matches: vs Roth (earlier date, returned first by
        _match_for_one) and vs Wolf (later date). The message poster is 'Ed Wolf',
        so the loser should be Wolf, not Roth.
        """
        Match.objects.create(
            season=self.season, player1=self.kanter, player2=self.wolf,
            tier=1, status=Match.STATUS_SCHEDULED,
            scheduled_date=datetime.date(2025, 4, 25),
        )
        results = self._parse_and_resolve(
            '[4/25, 8:00 PM] Ed Wolf: Kanter over me 8-5'
        )
        r = results[0]
        self.assertIsNone(r.error)
        self.assertEqual(r.winner, self.kanter)
        self.assertEqual(r.loser, self.wolf)

    def test_resolve_no_scheduled_match_for_pair_returns_error(self):
        """Both players are in the season but have no scheduled match — error is set."""
        # Roth and Wolf are both enrolled but have no match against each other.
        results = self._parse_and_resolve('Roth d Wolf 8-4')
        r = results[0]
        self.assertIsNotNone(r.error)
        self.assertIn('No scheduled match', r.error)
        self.assertIsNone(r.match)
        # Players are still resolved despite the error
        self.assertEqual(r.winner, self.roth)
        self.assertEqual(r.loser, self.wolf)

    def test_resolve_unknown_player_returns_error(self):
        """When player name cannot be matched, error is set."""
        results = self._parse_and_resolve('Zzzunknown d Aaaunknown 8-4')
        r = results[0]
        self.assertIsNotNone(r.error)
        self.assertIsNone(r.winner)

    def test_resolve_last_name_match(self):
        """Last-name-only match (e.g. 'Roth') resolves to the correct player."""
        results = self._parse_and_resolve('Kanter d Roth 8-4')
        r = results[0]
        self.assertEqual(r.winner, self.kanter)
        self.assertEqual(r.loser, self.roth)

    def test_resolve_already_completed_match_skipped_in_view(self):
        """Completed matches are not included in the scheduled list for resolution."""
        self.match_roth_kanter.status = Match.STATUS_COMPLETED
        self.match_roth_kanter.save()

        results = self._parse_and_resolve(
            '[4/24, 4:37 PM] +1 (555) 000-0005: T2 Kanter def Roth 8-4'
        )
        r = results[0]
        # No scheduled match for Kanter vs Roth → error
        self.assertIsNotNone(r.error)
        self.assertIsNone(r.match)
