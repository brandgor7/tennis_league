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


def _match_is_clickable(match):
    """A bracket match is worth opening only once it's a real contest.

    Future rounds are created up front with both players unset (TBD); linking to
    them leads to a detail page with no opponents and result actions that can't be
    used yet. Treat a match as clickable only when both players are known or it has
    already been decided (e.g. a bye/walkover).
    """
    if match is None or match.pk is None:
        return False
    return bool((match.player1_id and match.player2_id) or match.winner_id)


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
            slot.is_clickable = _match_is_clickable(slot.match)
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
                is_clickable=False,
            )
            slots.append(slot)

        rounds_data.append({
            'code': round_code,
            'label': _ROUND_LABELS[round_code],
            'col_index': round_idx + 1,
            'slots': slots,
        })

    return rounds_data, bracket_size


_CENTERED_ROW_PX = 48


def _winner_of(match):
    """Return the player advancing from a match, or None if undecided.

    A saved match advances only its recorded winner; a later-round match that
    holds just one player so far is still awaiting its opponent. In the live
    preview (no saved match), a structural bye is one-sided and auto-advances
    its lone player.
    """
    if match.winner_id:
        if match.player1_id == match.winner_id:
            return match.player1
        if match.player2_id == match.winner_id:
            return match.player2
    if match.pk is None and (match.player1 is None) != (match.player2 is None):
        return match.player1 or match.player2
    return None


def _winner_score(match):
    """Set scores from the winner's perspective, e.g. '6–3 6–4', or '' if not completed."""
    if getattr(match, 'status', None) != 'completed':
        return ''
    p1_won = match.player1_id == match.winner_id
    parts = []
    for s in match.sets.all():
        w = s.player1_games if p1_won else s.player2_games
        l = s.player2_games if p1_won else s.player1_games
        parts.append(f'{w}–{l}')
    return ' '.join(parts)


def _centered_layout(rounds_data, bracket_size):
    """
    Transform rounds_data (first round → final) into a centered bracket layout.

    Each player and each match winner becomes its own node. The two halves of
    the draw converge from the left and right onto a central champion node, with
    the winner of each match shown on the line where the two feeders meet.

    Returns {columns, rows, row_px, nodes} or None when not applicable.
    """
    if not rounds_data or bracket_size < 2:
        return None

    R = len(rounds_data)
    half = bracket_size // 2
    total_columns = 2 * R + 1
    center_col = R + 1
    nodes = []

    # Leaves — the individual first-round participants flanking each half.
    if R == 1:
        slot = rounds_data[0]['slots'][0]
        m = slot.match
        pk = m.pk if _match_is_clickable(m) else None
        nodes.append(_leaf_node(m.player1, slot.player1_seed, m.player1 is None,
                                1, 1, 'cb-left-straight', 0, pk))
        nodes.append(_leaf_node(m.player2, slot.player2_seed, m.player2 is None,
                                total_columns, 1, 'cb-right-straight', 0, pk))
    else:
        first_slots = rounds_data[0]['slots']
        mid = len(first_slots) // 2
        v = _CENTERED_ROW_PX // 2
        for grid_column, side, group in ((1, 'left', first_slots[:mid]),
                                         (total_columns, 'right', first_slots[mid:])):
            row = 1
            for slot in group:
                m = slot.match
                pk = m.pk if _match_is_clickable(m) else None
                nodes.append(_leaf_node(m.player1, slot.player1_seed, slot.is_bye,
                                        grid_column, row, f'cb-{side}-up', v, pk))
                nodes.append(_leaf_node(m.player2, slot.player2_seed, slot.is_bye,
                                        grid_column, row + 1, f'cb-{side}-down', v, pk))
                row += 2

    # Winner nodes — one per match, advancing toward the centre.
    for r in range(R):
        slots = rounds_data[r]['slots']
        span = 2 ** (r + 1)
        if r == R - 1:
            m = slots[0].match
            nodes.append({
                'kind': 'champion',
                'player': _winner_of(m),
                'seed': None,
                'is_bye': False,
                'grid_column': center_col,
                'row_start': 1,
                'row_end': half + 1,
                'connector': '',
                'v_px': 0,
                'score': _winner_score(m),
                'match_pk': m.pk if _match_is_clickable(m) else None,
            })
            continue

        left_count = len(slots) // 2
        for k, slot in enumerate(slots):
            m = slot.match
            if k < left_count:
                side, local, grid_column = 'left', k, r + 2
            else:
                side, local, grid_column = 'right', k - left_count, total_columns - (r + 1)
            if span == half:  # this round's winners are the finalists
                connector, v_px = f'cb-{side}-straight', 0
            else:
                connector = f'cb-{side}-{"up" if local % 2 == 0 else "down"}'
                v_px = span * _CENTERED_ROW_PX // 2
            nodes.append({
                'kind': 'winner',
                'player': _winner_of(m),
                'seed': None,
                'is_bye': False,
                'grid_column': grid_column,
                'row_start': local * span + 1,
                'row_end': (local + 1) * span + 1,
                'connector': connector,
                'v_px': v_px,
                'score': _winner_score(m),
                'match_pk': m.pk if _match_is_clickable(m) else None,
            })

    return {
        'columns': total_columns,
        'rows': half,
        'row_px': _CENTERED_ROW_PX,
        'nodes': nodes,
    }


def _leaf_node(player, seed, is_bye, grid_column, row, connector, v_px, match_pk):
    return {
        'kind': 'leaf',
        'player': player,
        'seed': seed,
        'is_bye': is_bye and player is None,
        'grid_column': grid_column,
        'row_start': row,
        'row_end': row + 1,
        'connector': connector,
        'v_px': v_px,
        'score': '',
        'match_pk': match_pk,
    }


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

        tiers_data = []
        for t in range(1, season.num_tiers + 1):
            bracket = brackets_by_tier.get(t)

            if bracket:
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
                'centered': _centered_layout(rounds_data, bracket_size),
            })

        ctx.update({
            'season': season,
            'tiers_data': tiers_data,
            'multi_tier': season.num_tiers > 1,
            'bracket_style': season.playoff_bracket_style,
        })
        return ctx
