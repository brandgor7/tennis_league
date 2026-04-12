"""
Management command: seed

Clears the database and populates it with a realistic mid-season sample
league, useful for local development and browser testing.

Usage:
    python manage.py seed                  # prompts for confirmation
    python manage.py seed --noinput        # skips prompt (CI-friendly)

Created data
------------
Admin:     username=admin  password=admin
Players:   12 players across 2 tiers, password=tennis123
Season:    "Spring 2025", active, 2 tiers, best-of-3
Matches:   10 completed + 3 scheduled per tier
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from leagues.models import Season, SeasonPlayer, Tier
from matches.models import Match, MatchSet

User = get_user_model()

# ---------------------------------------------------------------------------
# Static data
# ---------------------------------------------------------------------------

TIER1_PLAYERS = [
    ('djokovic',  'Novak',   'Djokovic'),
    ('nadal',     'Rafael',  'Nadal'),
    ('federer',   'Roger',   'Federer'),
    ('murray',    'Andy',    'Murray'),
    ('sampras',   'Pete',    'Sampras'),
    ('agassi',    'Andre',   'Agassi'),
]

TIER2_PLAYERS = [
    ('hewitt',  'Lleyton',  'Hewitt'),
    ('edberg',  'Stefan',   'Edberg'),
    ('safin',   'Marat',    'Safin'),
    ('rafter',  'Patrick',  'Rafter'),
    ('henman',  'Tim',      'Henman'),
    ('becker',  'Boris',    'Becker'),
]


class Command(BaseCommand):
    help = 'Seed the database with sample league data for local preview.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--noinput',
            action='store_true',
            help='Do not prompt for confirmation before clearing existing data.',
        )

    def handle(self, *args, **options):
        if not options['noinput']:
            confirm = input(
                'This will delete ALL existing data and reseed. Continue? [y/N] '
            )
            if confirm.strip().lower() != 'y':
                self.stdout.write('Aborted.')
                return

        self._clear()
        self._create_admin()
        season = self._create_season()
        tier1, tier2 = self._create_players(season)
        self._create_tier1_matches(season, tier1)
        self._create_tier2_matches(season, tier2)
        self.stdout.write(self.style.SUCCESS(
            '\nSeed complete. Log in at /accounts/login/ with admin / admin'
        ))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear(self):
        MatchSet.objects.all().delete()
        Match.objects.all().delete()
        SeasonPlayer.objects.all().delete()
        Season.objects.all().delete()
        User.objects.all().delete()
        self.stdout.write('Cleared existing data.')

    def _create_admin(self):
        User.objects.create_superuser(
            username='admin',
            password='admin',
            first_name='Admin',
            last_name='User',
        )
        self.stdout.write('  admin user    username=admin   password=admin')

    def _create_season(self):
        season = Season.objects.create(
            name='Spring 2025',
            year=2025,
            status=Season.STATUS_ACTIVE,
            sets_to_win=2,
            final_set_format=Season.FINAL_SET_FULL,
            playoff_qualifiers_count=4,
            walkover_rule=Season.WALKOVER_WINNER,
            postponement_deadline=14,
            points_for_win=3,
            points_for_loss=0,
            points_for_walkover_loss=0,
        )
        Tier.objects.create(season=season, number=1, name='Tier 1')
        Tier.objects.create(season=season, number=2, name='Tier 2')
        self.stdout.write(f'  season        "{season}"')
        return season

    def _create_players(self, season):
        tier1, tier2 = [], []
        for username, first, last in TIER1_PLAYERS:
            u = User.objects.create_user(
                username=username, password='tennis123',
                first_name=first, last_name=last,
            )
            SeasonPlayer.objects.create(season=season, player=u, tier=1)
            tier1.append(u)
        for username, first, last in TIER2_PLAYERS:
            u = User.objects.create_user(
                username=username, password='tennis123',
                first_name=first, last_name=last,
            )
            SeasonPlayer.objects.create(season=season, player=u, tier=2)
            tier2.append(u)
        self.stdout.write(
            f'  players       {len(tier1)} in tier 1, {len(tier2)} in tier 2'
            '  (password=tennis123)'
        )
        return tier1, tier2

    def _create_tier1_matches(self, season, tier1):
        djokovic, nadal, federer, murray, sampras, agassi = tier1
        today = datetime.date.today()

        # Completed matches — first player listed is the winner.
        # Sets: (p1_games, p2_games) or (p1_games, p2_games, tb_p1, tb_p2)
        completed = [
            (djokovic, nadal,    [(6,4), (6,2)],          35),
            (djokovic, federer,  [(7,5), (6,3)],          28),
            (djokovic, murray,   [(6,2), (6,1)],          21),
            (nadal,    federer,  [(6,4), (4,6), (6,3)],   30),
            (nadal,    murray,   [(6,3), (6,4)],          24),
            (nadal,    sampras,  [(7,5), (6,4)],          17),
            (federer,  murray,   [(6,4), (6,3)],          20),
            (federer,  agassi,   [(6,2), (6,1)],          13),
            (murray,   sampras,  [(7,5), (6,3)],          16),
            (sampras,  agassi,   [(6,3), (6,4)],           9),
        ]
        for winner, loser, sets, days_ago in completed:
            self._make_completed(season, winner, loser, sets, today - datetime.timedelta(days=days_ago), 1)

        # Scheduled matches
        for days_ahead, p1, p2 in [
            ( 7, djokovic, agassi),
            (10, nadal,    agassi),
            (14, federer,  sampras),
        ]:
            Match.objects.create(
                season=season, player1=p1, player2=p2, tier=1,
                status=Match.STATUS_SCHEDULED,
                scheduled_date=today + datetime.timedelta(days=days_ahead),
            )
        self.stdout.write('  tier 1        10 completed, 3 scheduled')

    def _create_tier2_matches(self, season, tier2):
        hewitt, edberg, safin, rafter, henman, becker = tier2
        today = datetime.date.today()

        completed = [
            (hewitt, becker,  [(6,3), (7,5)],             32),
            (hewitt, safin,   [(6,4), (6,2)],             25),
            (hewitt, edberg,  [(4,6), (6,3), (6,4)],      18),
            (edberg, becker,  [(6,4), (6,2)],             28),
            (edberg, henman,  [(6,3), (6,1)],             22),
            (edberg, rafter,  [(7,5), (6,4)],             15),
            (safin,  becker,  [(6,2), (6,3)],             26),
            (safin,  henman,  [(7,5), (6,4)],             19),
            (rafter, becker,  [(6,4), (7,6,7,4)],         12),
            (rafter, henman,  [(6,3), (6,4)],              8),
        ]
        for winner, loser, sets, days_ago in completed:
            self._make_completed(season, winner, loser, sets, today - datetime.timedelta(days=days_ago), 2)

        for days_ahead, p1, p2 in [
            ( 5, hewitt,  henman),
            ( 9, safin,   rafter),
            (12, edberg,  safin),
        ]:
            Match.objects.create(
                season=season, player1=p1, player2=p2, tier=2,
                status=Match.STATUS_SCHEDULED,
                scheduled_date=today + datetime.timedelta(days=days_ahead),
            )
        self.stdout.write('  tier 2        10 completed, 3 scheduled')

    def _make_completed(self, season, winner, loser, sets, played_date, tier):
        """Create a completed Match with MatchSet rows. winner is always p1."""
        match = Match.objects.create(
            season=season,
            player1=winner,
            player2=loser,
            tier=tier,
            status=Match.STATUS_COMPLETED,
            winner=winner,
            played_date=played_date,
            entered_by=winner,
            confirmed_by=loser,
        )
        for i, set_data in enumerate(sets, 1):
            p1g, p2g = set_data[0], set_data[1]
            tb1 = set_data[2] if len(set_data) > 2 else None
            tb2 = set_data[3] if len(set_data) > 3 else None
            MatchSet.objects.create(
                match=match,
                set_number=i,
                player1_games=p1g,
                player2_games=p2g,
                tiebreak_player1_points=tb1,
                tiebreak_player2_points=tb2,
            )
        return match
