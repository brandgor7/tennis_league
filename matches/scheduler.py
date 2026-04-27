from datetime import timedelta

from django.db import transaction

from leagues.models import Season, SeasonPlayer
from .models import Match


_ROUND_OFFSETS = {
    Season.SCHEDULE_SINGLE_DAY: timedelta(days=0),
    Season.SCHEDULE_CONSECUTIVE_DAYS: timedelta(days=1),
    Season.SCHEDULE_WEEKLY: timedelta(weeks=1),
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
            p2 = rotating[n - 1 - i]
            if p1 is not None and p2 is not None:
                pairs.append((p1, p2))
        rounds.append(pairs)
        rotating = [rotating[-1]] + rotating[:-1]

    return rounds


def existing_pairs(season, tier):
    """
    Return the set of matchup pairs that should not be re-scheduled for a tier.

    Includes pairs from the current season and, if season.preseason is set,
    from the attached preseason — so players who already met in the preseason
    are also excluded from the new schedule.
    """
    season_ids = [season.pk]
    if season.preseason_id:
        season_ids.append(season.preseason_id)
    pairs = set()
    for row in Match.objects.filter(
        season_id__in=season_ids, tier=tier, round=Match.ROUND_REGULAR
    ).values('player1_id', 'player2_id'):
        pairs.add(frozenset([row['player1_id'], row['player2_id']]))
    return pairs


def remaining_rounds_count(season, tier):
    """Return the number of unscheduled rounds remaining for a tier."""
    player_ids = list(
        SeasonPlayer.objects.filter(season=season, tier=tier, is_active=True)
        .values_list('player_id', flat=True)
    )
    existing = existing_pairs(season, tier)
    count = 0
    for round_pairs in _round_robin_rounds(player_ids):
        if any(frozenset([p1, p2]) not in existing for p1, p2 in round_pairs):
            count += 1
    return count


@transaction.atomic
def generate_schedule(season, start_date, num_rounds):
    """
    Generate scheduled Match objects for all tiers in a season.

    Can be called multiple times. Already-scheduled matchup pairs are skipped
    so no pair is ever duplicated within a season. The start_date and round
    offsets apply to the first newly-added round (round_index 0).

    Each round's date is determined by season.schedule_type:
      - single_day:        all matches on start_date
      - consecutive_days:  rounds advance one day per round
      - weekly:            rounds advance one week per round

    num_rounds is capped per tier at the remaining unscheduled rounds available.

    Returns the list of newly created Match objects (may be empty if all
    possible rounds are already scheduled).
    """
    is_single_day = season.schedule_type == Season.SCHEDULE_SINGLE_DAY
    offset = _ROUND_OFFSETS[season.schedule_type]
    to_create = []

    for tier in range(1, season.num_tiers + 1):
        player_ids = list(
            SeasonPlayer.objects.filter(season=season, tier=tier, is_active=True)
            .values_list('player_id', flat=True)
        )

        existing = existing_pairs(season, tier)
        remaining = []
        for round_pairs in _round_robin_rounds(player_ids):
            new_pairs = [(p1, p2) for p1, p2 in round_pairs if frozenset([p1, p2]) not in existing]
            if new_pairs:
                remaining.append(new_pairs)

        for round_index, pairs in enumerate(remaining[:num_rounds]):
            scheduled_date = start_date if is_single_day else start_date + offset * round_index

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
