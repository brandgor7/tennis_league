import types

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from leagues.models import Season
from .generator import _ROUND_SEQUENCE, _ROUND_FOR_SIZE, _seed_order, bracket_size_for
from .models import PlayoffBracket
from matches.models import Match
from standings.calculator import calculate_standings


_ROUND_LABELS = {
    Match.ROUND_R32: 'Round of 32',
    Match.ROUND_R16: 'Round of 16',
    Match.ROUND_QF: 'Quarterfinal',
    Match.ROUND_SF: 'Semifinal',
    Match.ROUND_FINAL: 'Final',
}


def _bracket_context(bracket):
    """
    Build the rounds_data and bracket_size needed to render a bracket.

    Returns (rounds_data, bracket_size) where rounds_data is a list of dicts:
      {code, label, slots, col_index}
    and each slot has .grid_row_start / .grid_row_end set.
    """
    slots_qs = (
        bracket.slots
        .select_related('match', 'match__player1', 'match__player2', 'match__winner')
        .prefetch_related('match__sets')
        .order_by('bracket_position')
    )

    by_round = {}
    for slot in slots_qs:
        by_round.setdefault(slot.round, []).append(slot)

    ordered_rounds = [(r, by_round[r]) for r in _ROUND_SEQUENCE if r in by_round]

    if not ordered_rounds:
        return [], 0

    first_round_count = len(ordered_rounds[0][1])
    bracket_size = first_round_count * 2
    last_col = len(ordered_rounds) - 1
    first_round_order = _seed_order(bracket_size)

    rounds_data = []
    for col_idx, (round_code, slots) in enumerate(ordered_rounds):
        n_matches = len(slots)
        span = bracket_size // n_matches
        is_final_round = (col_idx == last_col)
        for i, slot in enumerate(slots):
            slot.grid_row_start = i * span + 1
            slot.grid_row_end = (i + 1) * span + 1
            # connector_class drives ::after shape; empty string = no outgoing connector
            slot.connector_class = '' if is_final_round else ('bracket-upper' if i % 2 == 0 else 'bracket-lower')
            # v_connector_px: half the match height in px (row height = 52px)
            slot.v_connector_px = 0 if is_final_round else span * 26
            slot.has_incoming = col_idx > 0
            if col_idx == 0:
                slot.player1_seed = first_round_order[i * 2]
                slot.player2_seed = first_round_order[i * 2 + 1]
                slot.is_bye = (slot.match.player1 is None) != (slot.match.player2 is None)
            else:
                slot.player1_seed = None
                slot.player2_seed = None
                slot.is_bye = False
        rounds_data.append({
            'code': round_code,
            'label': _ROUND_LABELS[round_code],
            'col_index': col_idx + 1,
            'slots': slots,
        })

    return rounds_data, bracket_size


def _preview_context(season, tier_num):
    """
    Build rounds_data and bracket_size for a live preview based on current standings.
    Uses the same seeding logic as generate_bracket but creates no DB records.
    Only the first round has players; later rounds show TBD.
    """
    tier_obj = season.tiers.filter(number=tier_num).first()
    qualifiers_count = (
        tier_obj.playoff_qualifiers_count
        if tier_obj and tier_obj.playoff_qualifiers_count is not None
        else season.playoff_qualifiers_count
    )

    standings = calculate_standings(season, tier_num)
    max_q = min(qualifiers_count, len(standings))
    bracket_size = bracket_size_for(max_q)

    if bracket_size < 2:
        return [], 0

    qualifiers = [row['player'] for row in standings[:max_q]]
    first_round_code = _ROUND_FOR_SIZE[bracket_size]
    first_round_idx = _ROUND_SEQUENCE.index(first_round_code)
    rounds = _ROUND_SEQUENCE[first_round_idx:]
    order = _seed_order(bracket_size)
    last_col = len(rounds) - 1

    # bye_winners[match_idx] = player if that first-round slot is a bye, else None.
    # Used to pre-populate the second round where both feeders are byes.
    bye_winners = {}

    rounds_data = []
    for round_idx, round_code in enumerate(rounds):
        n_matches = bracket_size // (2 ** (round_idx + 1))
        span = bracket_size // n_matches
        is_final_round = (round_idx == last_col)

        slots = []
        for match_idx in range(n_matches):
            if round_idx == 0:
                p1_seed = order[match_idx * 2]
                p2_seed = order[match_idx * 2 + 1]
                p1 = qualifiers[p1_seed - 1] if p1_seed <= len(qualifiers) else None
                p2 = qualifiers[p2_seed - 1] if p2_seed <= len(qualifiers) else None
                bye_winners[match_idx] = (p1 or p2) if (p1 is None) != (p2 is None) else None
            elif round_idx == 1:
                p1_seed = None
                p2_seed = None
                p1 = bye_winners.get(match_idx * 2)
                p2 = bye_winners.get(match_idx * 2 + 1)
            else:
                p1_seed = None
                p2_seed = None
                p1 = None
                p2 = None

            match = types.SimpleNamespace(
                player1=p1,
                player2=p2,
                winner_id=None,
                player1_id=p1.pk if p1 else None,
                player2_id=p2.pk if p2 else None,
                status='scheduled',
                pk=None,
                sets=types.SimpleNamespace(all=lambda: []),
            )
            slot = types.SimpleNamespace(
                match=match,
                bracket_position=match_idx + 1,
                round=round_code,
                grid_row_start=match_idx * span + 1,
                grid_row_end=(match_idx + 1) * span + 1,
                connector_class='' if is_final_round else ('bracket-upper' if match_idx % 2 == 0 else 'bracket-lower'),
                v_connector_px=0 if is_final_round else span * 26,
                has_incoming=round_idx > 0,
                player1_seed=p1_seed,
                player2_seed=p2_seed,
                is_bye=round_idx == 0 and (p1 is None) != (p2 is None),
            )
            slots.append(slot)

        rounds_data.append({
            'code': round_code,
            'label': _ROUND_LABELS[round_code],
            'col_index': round_idx + 1,
            'slots': slots,
        })

    return rounds_data, bracket_size


class PlayoffView(TemplateView):
    template_name = 'playoffs/bracket.html'

    def get(self, request, *args, **kwargs):
        season = get_object_or_404(Season, slug=kwargs['slug'])
        is_staff = request.user.is_authenticated and request.user.is_staff
        if not season.playoffs_public and not is_staff:
            raise PermissionDenied
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        season = get_object_or_404(Season.objects.prefetch_related('tiers'), slug=self.kwargs['slug'])

        brackets_by_tier = {
            b.tier: b for b in PlayoffBracket.objects.filter(season=season)
        }
        tiers_by_num = {t.number: t for t in season.tiers.all()}

        tiers_data = []
        for t in range(1, season.num_tiers + 1):
            tier_obj = tiers_by_num.get(t)
            is_playoffs = tier_obj.is_playoffs if tier_obj else False
            bracket = brackets_by_tier.get(t)

            if is_playoffs and bracket:
                rounds_data, bracket_size = _bracket_context(bracket)
                is_preview = False
            elif season.playoffs_enabled:
                rounds_data, bracket_size = _preview_context(season, t)
                is_preview = True
                bracket = None
            else:
                rounds_data, bracket_size = [], 0
                is_preview = False

            tiers_data.append({
                'tier_num': t,
                'tier_name': season.tier_name(t),
                'bracket': bracket,
                'rounds_data': rounds_data,
                'bracket_size': bracket_size,
                'num_rounds': len(rounds_data),
                'is_preview': is_preview,
            })

        ctx.update({
            'season': season,
            'tiers_data': tiers_data,
            'multi_tier': season.num_tiers > 1,
        })
        return ctx
