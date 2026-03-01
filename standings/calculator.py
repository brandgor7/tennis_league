from leagues.models import SeasonPlayer
from matches.models import Match


def calculate_standings(season, tier):
    """
    Return a ranked list of dicts for all active players in the given season/tier.

    Each dict contains:
        player, played, wins, losses, points, sets_won, sets_lost,
        sets_ratio, games_won, games_lost, games_ratio
    """
    season_players = (
        SeasonPlayer.objects
        .filter(season=season, tier=tier, is_active=True)
        .select_related('player')
    )

    completed_matches = Match.objects.filter(
        season=season,
        tier=tier,
        status__in=[Match.STATUS_COMPLETED, Match.STATUS_WALKOVER],
    ).prefetch_related('sets')

    rows = []
    for sp in season_players:
        player = sp.player

        player_matches = [
            m for m in completed_matches
            if m.player1_id == player.pk or m.player2_id == player.pk
        ]

        wins = 0
        losses = 0
        walkover_losses = 0
        sets_won = 0
        sets_lost = 0
        games_won = 0
        games_lost = 0

        for match in player_matches:
            is_player1 = match.player1_id == player.pk

            if match.status == Match.STATUS_WALKOVER:
                if match.winner_id == player.pk:
                    wins += 1
                else:
                    losses += 1
                    walkover_losses += 1
                # Walkovers have no set/game data
                continue

            # Completed match — accumulate set/game totals
            for s in match.sets.all():
                if is_player1:
                    p_games = s.player1_games
                    o_games = s.player2_games
                else:
                    p_games = s.player2_games
                    o_games = s.player1_games

                games_won += p_games
                games_lost += o_games

                if p_games > o_games:
                    sets_won += 1
                else:
                    sets_lost += 1

            if match.winner_id == player.pk:
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

        sets_ratio = sets_won / sets_played if sets_played else 0.0
        games_ratio = games_won / games_played if games_played else 0.0

        rows.append({
            'player': player,
            'played': played,
            'wins': wins,
            'losses': losses,
            'points': points,
            'sets_won': sets_won,
            'sets_lost': sets_lost,
            'sets_ratio': sets_ratio,
            'games_won': games_won,
            'games_lost': games_lost,
            'games_ratio': games_ratio,
        })

    rows.sort(key=lambda r: (
        -r['points'],
        -r['played'],
        -r['sets_ratio'],
        -r['games_ratio'],
    ))

    return rows
