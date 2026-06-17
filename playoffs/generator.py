import datetime
import math

from django.db import transaction

from standings.calculator import calculate_standings
from matches.models import Match
from .models import PlayoffBracket, PlayoffSlot


# Round code for a bracket of a given size
_ROUND_FOR_SIZE = {
    32: Match.ROUND_R32,
    16: Match.ROUND_R16,
    8: Match.ROUND_QF,
    4: Match.ROUND_SF,
    2: Match.ROUND_FINAL,
}

# Ordered list of rounds from first to last
_ROUND_SEQUENCE = [Match.ROUND_R32, Match.ROUND_R16, Match.ROUND_QF, Match.ROUND_SF, Match.ROUND_FINAL]


def bracket_size_for(n_qualifiers):
    """Return the smallest power-of-2 >= n_qualifiers, or 0 if fewer than 2."""
    return 2 ** math.ceil(math.log2(n_qualifiers)) if n_qualifiers >= 2 else 0


def _seed_order(n):
    """
    Return the 1-indexed seed positions in bracket slot order for a bracket of size n.
    Consecutive pairs are first-round opponents.
    """
    if n == 1:
        return [1]
    prev = _seed_order(n // 2)
    result = []
    for s in prev:
        result.append(s)
        result.append(n + 1 - s)
    return result


def generate_bracket(season, tier, generated_by, start_date=None):
    """
    Generate a playoff bracket for the given season and tier.

    Takes the top players from standings (up to the tier's or season's
    playoff_qualifiers_count), sizes the bracket to the smallest power-of-2
    that fits all qualifiers, seeds matches with byes for unfilled positions,
    and links slots for winner advancement.

    If start_date is provided, round 1 is scheduled on that date and each
    subsequent round is scheduled season.playoff_interval_days later.

    Returns the created PlayoffBracket.
    Raises ValueError if a bracket already exists or there are fewer than 2 qualifiers.
    """
    if PlayoffBracket.objects.filter(season=season, tier=tier).exists():
        raise ValueError(f'A bracket for Tier {tier} already exists for this season.')

    tier_obj = season.tiers.filter(number=tier).first()
    qualifiers_count = (
        tier_obj.playoff_qualifiers_count
        if tier_obj and tier_obj.playoff_qualifiers_count is not None
        else season.playoff_qualifiers_count
    )

    standings = calculate_standings(season, tier)
    max_qualifiers = min(qualifiers_count, len(standings))

    if max_qualifiers < 2:
        raise ValueError('Not enough players to generate a bracket (minimum 2 required).')

    bracket_size = bracket_size_for(max_qualifiers)
    qualifiers = [row['participant'].members.first() for row in standings[:max_qualifiers]]

    first_round_code = _ROUND_FOR_SIZE[bracket_size]
    first_round_idx = _ROUND_SEQUENCE.index(first_round_code)
    rounds = _ROUND_SEQUENCE[first_round_idx:]

    order = _seed_order(bracket_size)
    interval = season.playoff_interval_days if start_date else 0

    with transaction.atomic():
        bracket = PlayoffBracket.objects.create(
            season=season,
            tier=tier,
            generated_by=generated_by,
        )

        prev_slots = []
        bye_matches = []

        for round_idx, round_code in enumerate(rounds):
            n_matches = bracket_size // (2 ** (round_idx + 1))
            current_slots = []
            round_date = start_date + datetime.timedelta(days=round_idx * interval) if start_date else None

            for match_idx in range(n_matches):
                if round_idx == 0:
                    p1_seed = order[match_idx * 2]
                    p2_seed = order[match_idx * 2 + 1]
                    p1 = qualifiers[p1_seed - 1] if p1_seed <= len(qualifiers) else None
                    p2 = qualifiers[p2_seed - 1] if p2_seed <= len(qualifiers) else None
                else:
                    p1 = None
                    p2 = None

                match = Match.objects.create(
                    season=season,
                    tier=tier,
                    round=round_code,
                    player1=p1,
                    player2=p2,
                    status=Match.STATUS_SCHEDULED,
                    scheduled_date=round_date,
                )
                slot = PlayoffSlot.objects.create(
                    bracket=bracket,
                    match=match,
                    bracket_position=match_idx + 1,
                    round=round_code,
                )
                current_slots.append(slot)

                if round_idx == 0 and (p1 is None) != (p2 is None):
                    bye_matches.append(match)

            for i, prev_slot in enumerate(prev_slots):
                prev_slot.next_slot = current_slots[i // 2]
                prev_slot.save(update_fields=['next_slot'])

            prev_slots = current_slots

        # Complete bye matches now that next_slot links are wired.
        # The post_save signal advances each bye winner into the next round.
        for match in bye_matches:
            match.winner = match.player1 or match.player2
            match.status = Match.STATUS_WALKOVER
            match.save()

    return bracket
