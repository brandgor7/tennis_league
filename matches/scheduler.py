from datetime import timedelta

from django.db import transaction

from leagues.models import SeasonPlayer
from .models import Match


_ROUND_OFFSETS = {
    'single_day': timedelta(days=0),
    'consecutive_days': timedelta(days=1),
    'weekly': timedelta(weeks=1),
}


def _round_robin_rounds(player_ids):
    """
    Generate all possible rounds for a round-robin schedule using the circle method.
    Returns a list of rounds; each round is a list of (player1_id, player2_id) tuples.
    Players assigned a bye in a given round (odd total count) are omitted from that round.
    """
    players = list(player_ids)
    n = len(players)
    if n < 2:
        return []

    if n % 2 == 1:
        players.append(None)
        n += 1

    fixed = players[0]
    rotating = players[1:]
    rounds = []

    for _ in range(n - 1):
        pairs = []
        if fixed is not None and rotating[0] is not None:
            pairs.append((fixed, rotating[0]))
        for i in range(1, n // 2):
            p1 = rotating[i]
            p2 = rotating[n - 2 - i]
            if p1 is not None and p2 is not None:
                pairs.append((p1, p2))
        rounds.append(pairs)
        rotating = [rotating[-1]] + rotating[:-1]

    return rounds


@transaction.atomic
def generate_schedule(season, start_date, num_rounds):
    """
    Generate scheduled Match objects for all tiers in a season.

    Builds a round-robin across all active players in each tier so no pair
    is scheduled more than once. Each round's date is determined by
    season.schedule_type:
      - single_day:        all matches on start_date
      - consecutive_days:  rounds advance one day per round
      - weekly:            rounds advance one week per round

    num_rounds is capped per tier at the maximum number of unique-matchup
    rounds available for that tier's player count (N players → N-1 rounds max).

    Returns the list of created Match objects.
    """
    offset = _ROUND_OFFSETS[season.schedule_type]
    to_create = []

    for tier in range(1, season.num_tiers + 1):
        player_ids = list(
            SeasonPlayer.objects.filter(season=season, tier=tier, is_active=True)
            .values_list('player_id', flat=True)
        )

        all_rounds = _round_robin_rounds(player_ids)
        scheduled_rounds = all_rounds[:num_rounds]

        for round_index, pairs in enumerate(scheduled_rounds):
            if season.schedule_type == season.SCHEDULE_SINGLE_DAY:
                scheduled_date = start_date
            else:
                scheduled_date = start_date + offset * round_index

            for player1_id, player2_id in pairs:
                to_create.append(Match(
                    season=season,
                    player1_id=player1_id,
                    player2_id=player2_id,
                    tier=tier,
                    round=Match.ROUND_REGULAR,
                    scheduled_date=scheduled_date,
                    status=Match.STATUS_SCHEDULED,
                ))

    return Match.objects.bulk_create(to_create)
