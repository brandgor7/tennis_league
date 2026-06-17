from django.db.models import Q

from leagues.models import Team
from matches.models import Match


def calculate_standings(season, tier):
    """
    Return a ranked list of dicts for all active teams in the given season/tier.

    Each dict contains: participant (Team), wins, losses, points, pd.

    Tiebreakers (not exposed in the dict): matches played, sets ratio, games ratio.
    """
    teams = list(
        Team.objects
        .filter(season=season, tier=tier, is_active=True)
        .prefetch_related('members')
    )

    team_ids = [t.pk for t in teams]

    completed_matches = list(
        Match.objects.filter(
            season=season,
            tier=tier,
            status__in=[Match.STATUS_COMPLETED, Match.STATUS_WALKOVER],
        ).filter(
            Q(team1_id__in=team_ids) | Q(team2_id__in=team_ids)
        ).prefetch_related('sets')
    )

    rows = []
    for team in teams:
        team_matches = [
            m for m in completed_matches
            if m.team1_id == team.pk or m.team2_id == team.pk
        ]

        wins = 0
        losses = 0
        walkover_losses = 0
        sets_won = 0
        sets_lost = 0
        games_won = 0
        games_lost = 0

        for match in team_matches:
            is_team1 = match.team1_id == team.pk

            if match.status == Match.STATUS_WALKOVER:
                if match.winning_team_id == team.pk:
                    wins += 1
                else:
                    losses += 1
                    walkover_losses += 1
                continue

            for s in match.sets.all():
                if is_team1:
                    p_games, o_games = s.player1_games, s.player2_games
                else:
                    p_games, o_games = s.player2_games, s.player1_games

                games_won += p_games
                games_lost += o_games

                if p_games > o_games:
                    sets_won += 1
                else:
                    sets_lost += 1

            if match.winning_team_id == team.pk:
                wins += 1
            else:
                losses += 1

        regular_losses = losses - walkover_losses
        points = (
            wins * season.points_for_win
            + walkover_losses * season.points_for_walkover_loss
            + regular_losses * season.points_for_loss
        )

        played = wins + losses
        sets_played = sets_won + sets_lost
        games_played = games_won + games_lost

        rows.append({
            'participant': team,
            'wins': wins,
            'losses': losses,
            'points': points,
            'pd': games_won - games_lost,
            '_played': played,
            '_sets_ratio': sets_won / sets_played if sets_played else 0.0,
            '_games_ratio': games_won / games_played if games_played else 0.0,
        })

    rows.sort(key=lambda r: (
        -r['points'],
        -r['_played'],
        -r['_sets_ratio'],
        -r['_games_ratio'],
    ))

    for row in rows:
        del row['_played']
        del row['_sets_ratio']
        del row['_games_ratio']

    return rows
