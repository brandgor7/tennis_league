from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from leagues.models import Season, SeasonPlayer
from matches.models import Match, MatchSet
from .calculator import calculate_standings

User = get_user_model()


# ─── Helpers ──────────────────────────────────────────────────────────────────

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
    return User.objects.create_user(
        username=username, first_name=first, last_name=last
    )


def enroll(season, player, tier=1, is_active=True):
    return SeasonPlayer.objects.create(
        season=season, player=player, tier=tier, is_active=is_active
    )


def completed_match(season, p1, p2, winner, tier=1, sets=None):
    """Create a completed Match with MatchSet records."""
    match = Match.objects.create(
        season=season,
        player1=p1, player2=p2,
        tier=tier,
        status=Match.STATUS_COMPLETED,
        winner=winner,
    )
    if sets is None:
        # Default: winner takes 6-4, 6-4
        if winner == p1:
            sets = [(6, 4), (6, 4)]
        else:
            sets = [(4, 6), (4, 6)]
    for i, (g1, g2) in enumerate(sets, start=1):
        MatchSet.objects.create(
            match=match, set_number=i,
            player1_games=g1, player2_games=g2,
        )
    return match


def walkover_match(season, p1, p2, winner, tier=1):
    """Create a walkover Match (no sets)."""
    return Match.objects.create(
        season=season,
        player1=p1, player2=p2,
        tier=tier,
        status=Match.STATUS_WALKOVER,
        winner=winner,
    )


# ─── calculator.calculate_standings tests ─────────────────────────────────────

class CalculateStandingsEmptyTest(TestCase):
    def setUp(self):
        self.season = make_season()

    def test_no_players_returns_empty_list(self):
        result = calculate_standings(self.season, tier=1)
        self.assertEqual(result, [])

    def test_players_with_no_matches_returns_rows_with_zeros(self):
        p = make_player('p1')
        enroll(self.season, p, tier=1)
        rows = calculate_standings(self.season, tier=1)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['played'], 0)
        self.assertEqual(row['wins'], 0)
        self.assertEqual(row['losses'], 0)
        self.assertEqual(row['points'], 0)
        self.assertEqual(row['sets_ratio'], 0.0)
        self.assertEqual(row['games_ratio'], 0.0)

    def test_inactive_player_excluded(self):
        active = make_player('active')
        inactive = make_player('inactive')
        enroll(self.season, active, tier=1, is_active=True)
        enroll(self.season, inactive, tier=1, is_active=False)
        rows = calculate_standings(self.season, tier=1)
        players = [r['player'] for r in rows]
        self.assertIn(active, players)
        self.assertNotIn(inactive, players)


class CalculateStandingsPointsTest(TestCase):
    def setUp(self):
        self.season = make_season(
            points_for_win=3,
            points_for_loss=0,
            points_for_walkover_loss=0,
        )
        self.p1 = make_player('p1')
        self.p2 = make_player('p2')
        enroll(self.season, self.p1, tier=1)
        enroll(self.season, self.p2, tier=1)

    def test_win_awards_points_for_win(self):
        completed_match(self.season, self.p1, self.p2, winner=self.p1)
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        self.assertEqual(p1_row['points'], 3)

    def test_loss_awards_no_points_by_default(self):
        completed_match(self.season, self.p1, self.p2, winner=self.p1)
        rows = calculate_standings(self.season, tier=1)
        p2_row = next(r for r in rows if r['player'] == self.p2)
        self.assertEqual(p2_row['points'], 0)

    def test_loss_awards_points_when_configured(self):
        self.season.points_for_loss = 1
        self.season.save()
        completed_match(self.season, self.p1, self.p2, winner=self.p1)
        rows = calculate_standings(self.season, tier=1)
        p2_row = next(r for r in rows if r['player'] == self.p2)
        self.assertEqual(p2_row['points'], 1)

    def test_wins_and_losses_counted(self):
        p3 = make_player('p3')
        enroll(self.season, p3, tier=1)
        completed_match(self.season, self.p1, self.p2, winner=self.p1)
        completed_match(self.season, self.p1, p3, winner=self.p1)
        completed_match(self.season, self.p2, p3, winner=self.p2)
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        self.assertEqual(p1_row['wins'], 2)
        self.assertEqual(p1_row['losses'], 0)
        self.assertEqual(p1_row['played'], 2)

    def test_multiple_matches_accumulate_points(self):
        p3 = make_player('p3')
        enroll(self.season, p3, tier=1)
        completed_match(self.season, self.p1, self.p2, winner=self.p1)
        completed_match(self.season, self.p1, p3, winner=self.p1)
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        self.assertEqual(p1_row['points'], 6)


class CalculateStandingsSetsGamesTest(TestCase):
    def setUp(self):
        self.season = make_season()
        self.p1 = make_player('p1')
        self.p2 = make_player('p2')
        enroll(self.season, self.p1, tier=1)
        enroll(self.season, self.p2, tier=1)

    def test_set_counts_accumulated(self):
        # p1 wins 6-4, 6-3 — p1 wins 2 sets, p2 wins 0
        completed_match(self.season, self.p1, self.p2, winner=self.p1,
                        sets=[(6, 4), (6, 3)])
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        p2_row = next(r for r in rows if r['player'] == self.p2)
        self.assertEqual(p1_row['sets_won'], 2)
        self.assertEqual(p1_row['sets_lost'], 0)
        self.assertEqual(p2_row['sets_won'], 0)
        self.assertEqual(p2_row['sets_lost'], 2)

    def test_game_counts_accumulated(self):
        completed_match(self.season, self.p1, self.p2, winner=self.p1,
                        sets=[(6, 4), (6, 3)])
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        p2_row = next(r for r in rows if r['player'] == self.p2)
        self.assertEqual(p1_row['games_won'], 12)
        self.assertEqual(p1_row['games_lost'], 7)
        self.assertEqual(p2_row['games_won'], 7)
        self.assertEqual(p2_row['games_lost'], 12)

    def test_sets_ratio_calculated(self):
        # p1 wins 2-0 in sets
        completed_match(self.season, self.p1, self.p2, winner=self.p1,
                        sets=[(6, 4), (6, 4)])
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        self.assertAlmostEqual(p1_row['sets_ratio'], 1.0)

    def test_games_ratio_calculated(self):
        completed_match(self.season, self.p1, self.p2, winner=self.p1,
                        sets=[(6, 4), (6, 4)])
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        # 12 won, 8 lost → 12/20 = 0.6
        self.assertAlmostEqual(p1_row['games_ratio'], 12 / 20)

    def test_no_sets_ratio_is_zero(self):
        """Player with no completed matches should have 0 ratios."""
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        self.assertEqual(p1_row['sets_ratio'], 0.0)
        self.assertEqual(p1_row['games_ratio'], 0.0)


class CalculateStandingsWalkoverTest(TestCase):
    def setUp(self):
        self.season = make_season(
            walkover_rule=Season.WALKOVER_WINNER,
            points_for_win=3,
            points_for_walkover_loss=0,
        )
        self.p1 = make_player('p1')
        self.p2 = make_player('p2')
        enroll(self.season, self.p1, tier=1)
        enroll(self.season, self.p2, tier=1)

    def test_walkover_win_counts_as_win(self):
        walkover_match(self.season, self.p1, self.p2, winner=self.p1)
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        self.assertEqual(p1_row['wins'], 1)
        self.assertEqual(p1_row['points'], 3)

    def test_walkover_loss_counts_as_loss_no_points(self):
        walkover_match(self.season, self.p1, self.p2, winner=self.p1)
        rows = calculate_standings(self.season, tier=1)
        p2_row = next(r for r in rows if r['player'] == self.p2)
        self.assertEqual(p2_row['losses'], 1)
        self.assertEqual(p2_row['points'], 0)

    def test_walkover_loss_gives_split_points(self):
        self.season.points_for_walkover_loss = 1
        self.season.save()
        walkover_match(self.season, self.p1, self.p2, winner=self.p1)
        rows = calculate_standings(self.season, tier=1)
        p2_row = next(r for r in rows if r['player'] == self.p2)
        self.assertEqual(p2_row['points'], 1)

    def test_walkover_does_not_affect_set_or_game_counts(self):
        walkover_match(self.season, self.p1, self.p2, winner=self.p1)
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        self.assertEqual(p1_row['sets_won'], 0)
        self.assertEqual(p1_row['games_won'], 0)


class CalculateStandingsRankingTest(TestCase):
    """Tiebreaker ordering: points → played → sets_ratio → games_ratio."""

    def setUp(self):
        self.season = make_season(points_for_win=3)
        self.p1 = make_player('p1')
        self.p2 = make_player('p2')
        self.p3 = make_player('p3')
        for p in [self.p1, self.p2, self.p3]:
            enroll(self.season, p, tier=1)

    def test_ranked_by_points_descending(self):
        completed_match(self.season, self.p1, self.p2, winner=self.p1)
        completed_match(self.season, self.p1, self.p3, winner=self.p1)
        completed_match(self.season, self.p2, self.p3, winner=self.p2)
        rows = calculate_standings(self.season, tier=1)
        players = [r['player'] for r in rows]
        self.assertEqual(players[0], self.p1)   # 6 pts
        self.assertEqual(players[1], self.p2)   # 3 pts
        self.assertEqual(players[2], self.p3)   # 0 pts

    def test_equal_points_tiebreak_by_matches_played(self):
        """Player with more matches played at equal points ranks higher."""
        p4 = make_player('p4')
        p5 = make_player('p5')
        enroll(self.season, p4, tier=1)
        enroll(self.season, p5, tier=1)
        # p1: beats p3, then loses to p4 → 3 pts, played=2
        completed_match(self.season, self.p1, self.p3, winner=self.p1)
        completed_match(self.season, p4, self.p1, winner=p4)
        # p2: beats p5 only → 3 pts, played=1
        completed_match(self.season, self.p2, p5, winner=self.p2)
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        p2_row = next(r for r in rows if r['player'] == self.p2)
        self.assertEqual(p1_row['points'], 3)
        self.assertEqual(p1_row['played'], 2)
        self.assertEqual(p2_row['points'], 3)
        self.assertEqual(p2_row['played'], 1)
        p1_pos = next(i for i, r in enumerate(rows) if r['player'] == self.p1)
        p2_pos = next(i for i, r in enumerate(rows) if r['player'] == self.p2)
        self.assertLess(p1_pos, p2_pos)

    def test_sets_ratio_tiebreaker(self):
        """When points and played are equal, better sets_ratio ranks higher."""
        p4 = make_player('p4')
        enroll(self.season, p4, tier=1)
        # p1 wins 2-0 in sets → sets_ratio = 1.0
        completed_match(self.season, self.p1, self.p3, winner=self.p1,
                        sets=[(6, 4), (6, 4)])
        # p2 wins 2-1 in sets → sets_ratio = 2/3 ≈ 0.667
        completed_match(self.season, self.p2, p4, winner=self.p2,
                        sets=[(6, 4), (3, 6), (6, 4)])
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        p2_row = next(r for r in rows if r['player'] == self.p2)
        # Confirm sets ratios are actually different
        self.assertAlmostEqual(p1_row['sets_ratio'], 1.0)
        self.assertAlmostEqual(p2_row['sets_ratio'], 2 / 3)
        p1_pos = next(i for i, r in enumerate(rows) if r['player'] == self.p1)
        p2_pos = next(i for i, r in enumerate(rows) if r['player'] == self.p2)
        self.assertLess(p1_pos, p2_pos)

    def test_games_ratio_tiebreaker(self):
        """When points, played, and sets_ratio are equal, better games_ratio ranks higher."""
        p4 = make_player('p4')
        enroll(self.season, p4, tier=1)
        # p1 wins 6-1 6-1: sets_ratio=1.0, games_ratio=12/14≈0.857
        completed_match(self.season, self.p1, self.p3, winner=self.p1,
                        sets=[(6, 1), (6, 1)])
        # p2 wins 7-5 7-5: sets_ratio=1.0, games_ratio=14/24≈0.583
        completed_match(self.season, self.p2, p4, winner=self.p2,
                        sets=[(7, 5), (7, 5)])
        rows = calculate_standings(self.season, tier=1)
        p1_row = next(r for r in rows if r['player'] == self.p1)
        p2_row = next(r for r in rows if r['player'] == self.p2)
        # Confirm sets ratios are equal (1.0) so games_ratio is the decider
        self.assertAlmostEqual(p1_row['sets_ratio'], 1.0)
        self.assertAlmostEqual(p2_row['sets_ratio'], 1.0)
        self.assertGreater(p1_row['games_ratio'], p2_row['games_ratio'])
        p1_pos = next(i for i, r in enumerate(rows) if r['player'] == self.p1)
        p2_pos = next(i for i, r in enumerate(rows) if r['player'] == self.p2)
        self.assertLess(p1_pos, p2_pos)


class CalculateStandingsTierIsolationTest(TestCase):
    """Standings for tier 1 should not include tier 2 players or matches."""

    def setUp(self):
        self.season = make_season(num_tiers=2, points_for_win=3)
        self.p1 = make_player('t1p1')
        self.p2 = make_player('t1p2')
        self.p3 = make_player('t2p1')
        self.p4 = make_player('t2p2')
        enroll(self.season, self.p1, tier=1)
        enroll(self.season, self.p2, tier=1)
        enroll(self.season, self.p3, tier=2)
        enroll(self.season, self.p4, tier=2)

    def test_tier1_standings_excludes_tier2_players(self):
        rows = calculate_standings(self.season, tier=1)
        players = [r['player'] for r in rows]
        self.assertIn(self.p1, players)
        self.assertIn(self.p2, players)
        self.assertNotIn(self.p3, players)
        self.assertNotIn(self.p4, players)

    def test_tier2_standings_excludes_tier1_players(self):
        rows = calculate_standings(self.season, tier=2)
        players = [r['player'] for r in rows]
        self.assertNotIn(self.p1, players)
        self.assertIn(self.p3, players)

    def test_tier2_match_not_counted_in_tier1_standings(self):
        completed_match(self.season, self.p3, self.p4, winner=self.p3, tier=2)
        # p3 plays in tier2 — shouldn't affect tier1 at all
        rows = calculate_standings(self.season, tier=1)
        for row in rows:
            self.assertEqual(row['played'], 0)

    def test_tier1_match_not_counted_in_tier2_standings(self):
        completed_match(self.season, self.p1, self.p2, winner=self.p1, tier=1)
        rows = calculate_standings(self.season, tier=2)
        for row in rows:
            self.assertEqual(row['played'], 0)

    def test_both_tiers_have_independent_standings(self):
        completed_match(self.season, self.p1, self.p2, winner=self.p1, tier=1)
        completed_match(self.season, self.p3, self.p4, winner=self.p4, tier=2)
        tier1 = calculate_standings(self.season, tier=1)
        tier2 = calculate_standings(self.season, tier=2)
        p1_row = next(r for r in tier1 if r['player'] == self.p1)
        p4_row = next(r for r in tier2 if r['player'] == self.p4)
        self.assertEqual(p1_row['wins'], 1)
        self.assertEqual(p4_row['wins'], 1)


class CalculateStandingsScheduledMatchesIgnoredTest(TestCase):
    """Only completed and walkover matches count."""

    def setUp(self):
        self.season = make_season()
        self.p1 = make_player('p1')
        self.p2 = make_player('p2')
        enroll(self.season, self.p1, tier=1)
        enroll(self.season, self.p2, tier=1)

    def test_scheduled_match_not_counted(self):
        Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            tier=1, status=Match.STATUS_SCHEDULED,
        )
        rows = calculate_standings(self.season, tier=1)
        for row in rows:
            self.assertEqual(row['played'], 0)

    def test_pending_confirmation_not_counted(self):
        Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            tier=1, status=Match.STATUS_PENDING,
        )
        rows = calculate_standings(self.season, tier=1)
        for row in rows:
            self.assertEqual(row['played'], 0)

    def test_cancelled_match_not_counted(self):
        Match.objects.create(
            season=self.season, player1=self.p1, player2=self.p2,
            tier=1, status=Match.STATUS_CANCELLED,
        )
        rows = calculate_standings(self.season, tier=1)
        for row in rows:
            self.assertEqual(row['played'], 0)


# ─── StandingsView tests ───────────────────────────────────────────────────────

class StandingsViewTest(TestCase):
    def setUp(self):
        self.season = make_season(num_tiers=1)
        self.url = reverse('leagues:standings', kwargs={'pk': self.season.pk})

    def test_standings_url_resolves(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_standings_404_for_missing_season(self):
        response = self.client.get(reverse('leagues:standings', kwargs={'pk': 99999}))
        self.assertEqual(response.status_code, 404)

    def test_standings_uses_correct_template(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, 'standings/standings.html')

    def test_season_in_context(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['season'], self.season)

    def test_tiers_in_context(self):
        response = self.client.get(self.url)
        self.assertIn('tiers', response.context)

    def test_single_tier_context_has_one_entry(self):
        response = self.client.get(self.url)
        self.assertEqual(len(response.context['tiers']), 1)

    def test_multi_tier_context_has_correct_count(self):
        season = make_season(num_tiers=2, name='Multi', status=Season.STATUS_UPCOMING)
        url = reverse('leagues:standings', kwargs={'pk': season.pk})
        response = self.client.get(url)
        self.assertEqual(len(response.context['tiers']), 2)

    def test_multi_tier_flag_true(self):
        season = make_season(num_tiers=2, name='Multi', status=Season.STATUS_UPCOMING)
        url = reverse('leagues:standings', kwargs={'pk': season.pk})
        response = self.client.get(url)
        self.assertTrue(response.context['multi_tier'])

    def test_single_tier_flag_false(self):
        response = self.client.get(self.url)
        self.assertFalse(response.context['multi_tier'])

    def test_standings_accessible_anonymously(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_standings_accessible_when_authenticated(self):
        user = User.objects.create_user(username='tester', password='pass')
        self.client.login(username='tester', password='pass')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_empty_standings_renders_no_error(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'No players')

    def test_player_name_appears_in_standings(self):
        p = make_player('alice', first='Alice', last='Smith')
        enroll(self.season, p, tier=1)
        response = self.client.get(self.url)
        self.assertContains(response, 'Alice Smith')

    def test_standings_shows_player_record(self):
        p1 = make_player('p1')
        p2 = make_player('p2')
        enroll(self.season, p1, tier=1)
        enroll(self.season, p2, tier=1)
        completed_match(self.season, p1, p2, winner=p1)
        response = self.client.get(self.url)
        # p1 has 1 win, p2 has 1 loss — check points appear
        self.assertContains(response, '3')  # points_for_win=3

    def test_multi_tier_shows_tier_tabs(self):
        season = make_season(num_tiers=2, name='Multi', status=Season.STATUS_UPCOMING)
        url = reverse('leagues:standings', kwargs={'pk': season.pk})
        response = self.client.get(url)
        self.assertContains(response, 'Tier 1')
        self.assertContains(response, 'Tier 2')

    def test_single_tier_has_no_tier_tabs(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Tier 1')


class HomeViewRedirectToStandingsTest(TestCase):
    """home() should redirect to standings once an active season exists."""

    def test_home_redirects_to_standings_when_active_season(self):
        season = Season.objects.create(
            name='Spring', year=2025, status=Season.STATUS_ACTIVE
        )
        response = self.client.get(reverse('home'))
        self.assertRedirects(
            response,
            reverse('leagues:standings', kwargs={'pk': season.pk}),
        )
