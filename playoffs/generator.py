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


def generate_bracket(season, tier, generated_by):
    """
    Generate a playoff bracket for the given season and tier.

    Takes the top players from standings (up to playoff_qualifiers_count),
    sizes the bracket to the largest power-of-2 that fits,
    seeds matches, and links slots for winner advancement.

    Returns the created PlayoffBracket.
    Raises ValueError if a bracket already exists or there are fewer than 2 qualifiers.
    """
    if PlayoffBracket.objects.filter(season=season, tier=tier).exists():
        raise ValueError(f'A bracket for Tier {tier} already exists for this season.')

    standings = calculate_standings(season, tier)
    max_qualifiers = min(season.playoff_qualifiers_count, len(standings))

    if max_qualifiers < 2:
        raise ValueError('Not enough players to generate a bracket (minimum 2 required).')

    # Largest power-of-2 ≤ max_qualifiers avoids the need for byes
    bracket_size = 2 ** int(math.log2(max_qualifiers))
    qualifiers = [row['player'] for row in standings[:bracket_size]]

    first_round_code = _ROUND_FOR_SIZE[bracket_size]
    first_round_idx = _ROUND_SEQUENCE.index(first_round_code)
    rounds = _ROUND_SEQUENCE[first_round_idx:]  # from first round to final

    order = _seed_order(bracket_size)  # seed positions in slot order

    with transaction.atomic():
        bracket = PlayoffBracket.objects.create(
            season=season,
            tier=tier,
            generated_by=generated_by,
        )

        prev_slots = []
        for round_idx, round_code in enumerate(rounds):
            n_matches = bracket_size // (2 ** (round_idx + 1))
            current_slots = []

            for match_idx in range(n_matches):
                if round_idx == 0:
                    p1 = qualifiers[order[match_idx * 2] - 1]
                    p2 = qualifiers[order[match_idx * 2 + 1] - 1]
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
                )
                slot = PlayoffSlot.objects.create(
                    bracket=bracket,
                    match=match,
                    bracket_position=match_idx + 1,
                    round=round_code,
                )
                current_slots.append(slot)

            # Wire previous round's slots to this round's slots
            for i, prev_slot in enumerate(prev_slots):
                prev_slot.next_slot = current_slots[i // 2]
                prev_slot.save(update_fields=['next_slot'])

            prev_slots = current_slots

    return bracket
